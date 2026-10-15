from fastapi.testclient import TestClient

from ride_app.interfaces.api import create_api

HERE = {"latitude": 0, "longitude": 0}


def register(client, car_type="sedan"):
    rider = client.post("/users", json={"name": "Alice"})
    assert rider.status_code == 201
    driver = client.post(
        "/drivers",
        json={
            "name": "Bob",
            "registration_number": " ka01 ",
            "car_type": car_type,
            "location": HERE,
        },
    )
    assert driver.status_code == 201
    return rider.json()["id"], driver.json()["id"]


def test_api_upgrade_coupon_completion_and_histories(app):
    with TestClient(create_api(app)) as client:
        user_id, driver_id = register(client)
        assert client.get(f"/users/{user_id}/rides").json() == []
        assert (
            client.post("/coupons", json={"code": "save10", "percentage": "10"}).status_code == 201
        )
        response = client.post(
            "/rides",
            json={
                "user_id": user_id,
                "pickup": HERE,
                "requested_type": "hatchback",
                "coupon_code": "save10",
            },
        )
        assert response.status_code == 201
        ride = response.json()
        assert ride["is_upgrade"] is True
        assert ride["requested_type"] == "hatchback" and ride["assigned_type"] == "sedan"
        assert ride["receipt"] is None
        assert ride["started_at"].endswith("Z")
        assert ride["terms"]["rate_card"]["minimum_fare"] == "50.00"
        assert client.delete("/coupons/SAVE10").status_code == 204
        complete = client.post(
            f"/rides/{ride['id']}/complete", json={"distance_km": "10", "dropoff": HERE}
        )
        assert complete.status_code == 200
        receipt = complete.json()["receipt"]
        assert receipt == {
            "distance_charge": "69.00",
            "minimum_fare_adjustment": "0.00",
            "discount": "6.90",
            "total": "62.10",
        }
        assert client.get(f"/rides/{ride['id']}").json() == complete.json()
        assert client.get(f"/users/{user_id}/rides").json() == [complete.json()]
        assert client.get(f"/drivers/{driver_id}/rides").json() == [complete.json()]
        repeat = client.post(
            f"/rides/{ride['id']}/complete",
            json={
                "distance_km": "999",
                "dropoff": {"latitude": 1, "longitude": 1},
            },
        )
        assert repeat.json() == complete.json()
        # Completion released the driver, and its canonical location can be updated.
        updated = client.patch(f"/drivers/{driver_id}/location", json=HERE)
        assert updated.json()["is_available"] is True
        assert updated.json()["cab"]["registration_number"] == "KA01"


def test_api_conflicts_and_errors_leave_state_intact(app):
    with TestClient(create_api(app)) as client:
        user_id, driver_id = register(client, car_type="hatchback")
        bad = client.post(
            "/rides",
            json={
                "user_id": user_id,
                "pickup": HERE,
                "requested_type": "hatchback",
                "coupon_code": "MISSING",
            },
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "INVALID_COUPON"
        assert client.get(f"/drivers/{driver_id}/rides").json() == []
        data = {"user_id": user_id, "pickup": HERE, "requested_type": "hatchback"}
        ride = client.post("/rides", json=data).json()
        assert client.post("/rides", json=data).status_code == 409
        assert (
            client.post(
                f"/rides/{ride['id']}/complete",
                json={
                    "distance_km": "-1",
                    "dropoff": HERE,
                },
            ).status_code
            == 422
        )
        assert client.get(f"/rides/{ride['id']}").json()["status"] == "ongoing"
        assert client.get("/users/unknown/rides").status_code == 404
        assert client.get("/rides/unknown").json()["error"]["code"] == "RIDE_NOT_FOUND"
        assert (
            client.patch(
                f"/drivers/{driver_id}/location",
                json={
                    "latitude": 91,
                    "longitude": 0,
                },
            ).json()["error"]["code"]
            == "INVALID_REQUEST"
        )
        assert client.post("/users", json={"name": " ", "unexpected": True}).status_code == 422
        assert client.get("/missing").json()["error"]["code"] == "HTTP_ERROR"


def test_api_no_driver_and_duplicate_resources(app):
    with TestClient(create_api(app)) as client:
        user_id, _ = register(client)
        duplicate = client.post(
            "/drivers",
            json={
                "name": "Other",
                "registration_number": "KA01",
                "car_type": "sedan",
                "location": HERE,
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "DUPLICATE_CAB"
        no_driver = client.post(
            "/rides",
            json={
                "user_id": user_id,
                "pickup": {"latitude": 50, "longitude": 50},
                "requested_type": "sedan",
            },
        )
        assert no_driver.status_code == 409
        assert no_driver.json()["error"]["code"] == "NO_DRIVER_AVAILABLE"
        coupon = {"code": "SAVE", "percentage": "100"}
        assert client.post("/coupons", json=coupon).status_code == 201
        assert client.post("/coupons", json=coupon).status_code == 409
        assert client.delete("/coupons/SAVE").status_code == 204
        assert client.delete("/coupons/SAVE").status_code == 204
        assert client.delete("/coupons/MISSING").status_code == 404


def test_health_documentation_and_openapi(app):
    with TestClient(create_api(app)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
        assert "RideResponse" in schema["components"]["schemas"]
        assert "/rides/{ride_id}/complete" in schema["paths"]
