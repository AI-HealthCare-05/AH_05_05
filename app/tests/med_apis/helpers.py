from httpx import AsyncClient

from app.models.supplement_nutrients import SupplementNutrient


async def authentication_headers(client: AsyncClient, email: str, phone_number: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "name": "영양제 테스트 사용자",
            "phone_number": phone_number,
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def create_supplement(food_code: str, name: str) -> SupplementNutrient:
    return await SupplementNutrient.create(
        food_code=food_code,
        name=name,
        basis_qty="500mg",
        energy_kcal=0,
        protein_g="0.00",
        carb_g="0.00",
        serving_desc="1정",
        serving_size="500mg",
        daily_freq="1회",
    )
