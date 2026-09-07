from httpx import AsyncClient
from starlette import status

from app.models.supplement_nutrients import SupplementNutrient
from app.tests.email_verification_helpers import with_signup_token


async def authentication_headers(client: AsyncClient, email: str, phone_number: str) -> dict[str, str]:
    signup = await client.post(
        "/api/v1/auth/signup",
        json=await with_signup_token(
            {
                "email": email,
                "password": "Password123!",
                "name": "영양제테스트사용자",
                "phone_number": phone_number,
                "birth_date": "1990-01-01",
                "gender": "FEMALE",
                "is_terms_agreed": True,
            }
        ),
    )
    # 가입이 조용히 실패하면 다음 줄 로그인에서 KeyError 로만 드러나 원인을 찾기 어렵다.
    # 필수 필드가 늘어난 것을 여기서 바로 알 수 있게 단언한다(#286).
    assert signup.status_code == status.HTTP_201_CREATED, signup.text

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
