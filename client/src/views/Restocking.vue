<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="successMessage" class="banner success-banner">{{ successMessage }}</div>
      <div v-if="submitError" class="banner error-banner">{{ submitError }}</div>

      <!-- Budget control -->
      <div class="card budget-card">
        <div class="budget-label">{{ t('restocking.budgetLabel') }}</div>
        <div class="budget-value">{{ money(budget) }}</div>
        <input
          type="range"
          class="budget-slider"
          min="0"
          max="200000"
          step="1000"
          v-model.number="budget"
        />
        <div class="slider-bounds">
          <span>{{ money(0) }}</span>
          <span>{{ money(200000) }}</span>
        </div>
      </div>

      <!-- Summary -->
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ recommendations.length }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ money(totalCost) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.budgetRemaining') }}</div>
          <div class="stat-value">{{ money(budgetRemaining) }}</div>
        </div>
      </div>

      <!-- Recommendations -->
      <div class="card">
        <div class="card-header recommendations-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
          <button
            class="place-order-btn"
            :disabled="recommendations.length === 0 || placing"
            @click="placeOrder"
          >
            {{ placing ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in recommendations" :key="row.sku">
                <td><strong>{{ row.sku }}</strong></td>
                <td>{{ translateProductName(row.name) }}</td>
                <td>
                  <span :class="['badge', row.trend]">{{ t(`trends.${row.trend}`) }}</span>
                </td>
                <td>{{ row.quantity.toLocaleString() }}</td>
                <td>{{ money(row.unit_price) }}</td>
                <td><strong>{{ money(row.lineTotal) }}</strong></td>
                <td>{{ t('orders.leadTimeDays', { days: row.leadDays }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

// Mirror of the backend's lead-time-by-trend map (server/main.py) for the preview column.
// The backend remains authoritative for the lead time actually stored on a submitted order.
const LEAD_TIME_BY_TREND = { increasing: 5, stable: 10, decreasing: 14 }
const DEFAULT_LEAD_TIME = 10

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const allForecasts = ref([])
    const budget = ref(50000)
    const placing = ref(false)
    const successMessage = ref('')
    const submitError = ref('')

    const money = (amount) => formatCurrency(amount, currentCurrency.value)

    const loadForecasts = async () => {
      try {
        loading.value = true
        allForecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load demand forecasts: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Recommend restock items within budget, prioritizing the largest demand gap.
    const recommendations = computed(() => {
      const eligible = allForecasts.value
        // Only items that actually need restocking (forecast exceeds current demand)
        .filter(f => f.forecasted_demand > f.current_demand)
        .map(f => {
          const quantity = f.forecasted_demand - f.current_demand
          return {
            sku: f.item_sku,
            name: f.item_name,
            trend: f.trend,
            quantity,
            unit_price: f.unit_cost,
            lineTotal: quantity * f.unit_cost,
            leadDays: LEAD_TIME_BY_TREND[f.trend] ?? DEFAULT_LEAD_TIME
          }
        })
        .sort((a, b) => b.quantity - a.quantity)

      // Greedy fill by largest gap. We SKIP an item that would exceed the budget but keep
      // checking the rest — a cheaper later item can still fit under the remaining budget.
      const selected = []
      let runningTotal = 0
      for (const item of eligible) {
        if (runningTotal + item.lineTotal <= budget.value) {
          selected.push(item)
          runningTotal += item.lineTotal
        }
      }
      return selected
    })

    const totalCost = computed(() =>
      recommendations.value.reduce((sum, r) => sum + r.lineTotal, 0)
    )

    const budgetRemaining = computed(() => budget.value - totalCost.value)

    const placeOrder = async () => {
      if (recommendations.value.length === 0 || placing.value) return
      placing.value = true
      submitError.value = ''
      successMessage.value = ''
      try {
        const order = await api.submitRestockingOrder({
          items: recommendations.value.map(r => ({
            sku: r.sku,
            name: r.name,
            quantity: r.quantity,
            unit_price: r.unit_price
          }))
        })
        successMessage.value = t('restocking.orderSuccess', { orderNumber: order.order_number })
      } catch (err) {
        console.error('Failed to submit restocking order:', err)
        submitError.value = t('restocking.orderError')
      } finally {
        placing.value = false
      }
    }

    onMounted(loadForecasts)

    return {
      t,
      loading,
      error,
      budget,
      placing,
      successMessage,
      submitError,
      recommendations,
      totalCost,
      budgetRemaining,
      money,
      translateProductName,
      placeOrder
    }
  }
}
</script>

<style scoped>
.banner {
  padding: 0.875rem 1.25rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
  font-size: 0.9rem;
  font-weight: 500;
}

.success-banner {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #15803d;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
}

.budget-card {
  margin-bottom: 1.5rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-value {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0.25rem 0 1rem;
}

.budget-slider {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.slider-bounds {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: #94a3b8;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.recommendations-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.place-order-btn {
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 0.625rem 1.25rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.empty-state {
  padding: 2rem 1.5rem;
  text-align: center;
  color: #64748b;
  font-size: 0.9rem;
}
</style>
