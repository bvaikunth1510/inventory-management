"""Tests for the restocking order endpoint (POST /api/restocking-orders)."""


class TestRestockingOrders:
    def test_submit_restocking_order(self, client):
        """Submitting items creates a Submitted order with the correct total."""
        payload = {
            "items": [
                {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 150, "unit_price": 12.50},
                {"sku": "GSK-203", "name": "High-Temperature Gasket", "quantity": 100, "unit_price": 3.25},
            ]
        }
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 200

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["customer"] == "Internal Restocking"
        assert order["order_number"].startswith("RST-")
        # 150 * 12.50 + 100 * 3.25 = 1875.00 + 325.00 = 2200.00
        assert order["total_value"] == 2200.00
        assert len(order["items"]) == 2

    def test_lead_time_uses_slowest_item_trend(self, client):
        """Expected delivery is gated by the slowest item's trend lead time.

        WDG-001 is 'increasing' (5 days) and CTL-330 is 'stable' (10 days),
        so the order's lead time should be 10 days.
        """
        from datetime import datetime

        payload = {
            "items": [
                {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 10, "unit_price": 12.50},
                {"sku": "CTL-330", "name": "Logic Controller Board", "quantity": 5, "unit_price": 95.00},
            ]
        }
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 200
        order = response.json()

        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])
        assert expected_delivery > order_date
        assert (expected_delivery - order_date).days == 10

    def test_submitted_order_appears_in_orders_list(self, client):
        """A submitted restocking order shows up in GET /api/orders."""
        payload = {
            "items": [
                {"sku": "FLT-405", "name": "Oil Filter Cartridge", "quantity": 150, "unit_price": 8.75},
            ]
        }
        created = client.post("/api/restocking-orders", json=payload).json()

        orders = client.get("/api/orders").json()
        ids = [o["id"] for o in orders]
        assert created["id"] in ids

        submitted = [o for o in orders if o["status"] == "Submitted"]
        assert any(o["id"] == created["id"] for o in submitted)

    def test_empty_items_rejected(self, client):
        """An empty items list is a 400 error."""
        response = client.post("/api/restocking-orders", json={"items": []})
        assert response.status_code == 400

    def test_demand_endpoint_includes_unit_cost(self, client):
        """The demand forecast now exposes unit_cost for pricing."""
        forecasts = client.get("/api/demand").json()
        assert len(forecasts) > 0
        for f in forecasts:
            assert "unit_cost" in f
            assert isinstance(f["unit_cost"], (int, float))
