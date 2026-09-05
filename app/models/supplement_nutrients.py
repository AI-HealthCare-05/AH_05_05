from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import MealSlot, SupplementStatus


def _standard_field(description: str) -> fields.DecimalField:
    return fields.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        description=description,
    )


class SupplementNutrient(models.Model):
    id = fields.BigIntField(primary_key=True)
    food_code = fields.CharField(max_length=20, unique=True)
    name = fields.CharField(max_length=100)
    basis_qty = fields.CharField(max_length=10)
    energy_kcal = fields.IntField()
    water_g = fields.DecimalField(max_digits=10, decimal_places=3, null=True)
    protein_g = fields.DecimalField(max_digits=5, decimal_places=2)
    fat_g = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    ash_g = fields.DecimalField(max_digits=10, decimal_places=3, null=True)
    carb_g = fields.DecimalField(max_digits=6, decimal_places=2)
    sugar_g = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    fiber_g = fields.DecimalField(max_digits=7, decimal_places=1, null=True)
    calcium_mg = fields.IntField(null=True)
    iron_mg = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    phosphorus_mg = fields.IntField(null=True)
    potassium_mg = fields.IntField(null=True)
    sodium_mg = fields.IntField(null=True)
    vitamin_a_ug_rae = fields.IntField(null=True)
    retinol_ug = fields.IntField(null=True)
    beta_carotene_ug = fields.IntField(null=True)
    thiamine_mg = fields.DecimalField(max_digits=6, decimal_places=3, null=True)
    riboflavin_mg = fields.DecimalField(max_digits=6, decimal_places=3, null=True)
    niacin_mg = fields.DecimalField(max_digits=6, decimal_places=3, null=True)
    vitamin_c_mg = fields.DecimalField(max_digits=7, decimal_places=2, null=True)
    vitamin_d_ug = fields.DecimalField(max_digits=7, decimal_places=2, null=True)
    cholesterol_mg = fields.DecimalField(max_digits=6, decimal_places=2, null=True)
    sat_fat_g = fields.DecimalField(max_digits=4, decimal_places=2, null=True)
    trans_fat_g = fields.DecimalField(max_digits=4, decimal_places=2, null=True)
    serving_desc = fields.CharField(max_length=10)
    serving_size = fields.CharField(max_length=10)
    daily_freq = fields.CharField(max_length=5)
    target = fields.CharField(max_length=10, null=True)

    class Meta:
        table = "supplement_nutrients"


class NutrientStandard(models.Model):
    id = fields.BigIntField(primary_key=True, description="영양소 섭취기준 ID")
    grp = fields.CharField(max_length=10, description="대상 구분")
    age = fields.CharField(max_length=20, null=True, description="연령 구간")

    carb_g_rni = _standard_field("탄수화물 권장섭취량(g/일)")
    carb_g_ai = _standard_field("탄수화물 충분섭취량(g/일)")
    carb_g_ul = _standard_field("탄수화물 상한섭취량(g/일)")
    protein_g_rni = _standard_field("단백질 권장섭취량(g/일)")
    protein_g_ai = _standard_field("단백질 충분섭취량(g/일)")
    protein_g_ul = _standard_field("단백질 상한섭취량(g/일)")
    fat_g_rni = _standard_field("지방 권장섭취량(g/일)")
    fat_g_ai = _standard_field("지방 충분섭취량(g/일)")
    fat_g_ul = _standard_field("지방 상한섭취량(g/일)")
    fiber_g_rni = _standard_field("식이섬유 권장섭취량(g/일)")
    fiber_g_ai = _standard_field("식이섬유 충분섭취량(g/일)")
    fiber_g_ul = _standard_field("식이섬유 상한섭취량(g/일)")
    calcium_mg_rni = _standard_field("칼슘 권장섭취량(mg/일)")
    calcium_mg_ai = _standard_field("칼슘 충분섭취량(mg/일)")
    calcium_mg_ul = _standard_field("칼슘 상한섭취량(mg/일)")
    iron_mg_rni = _standard_field("철 권장섭취량(mg/일)")
    iron_mg_ai = _standard_field("철 충분섭취량(mg/일)")
    iron_mg_ul = _standard_field("철 상한섭취량(mg/일)")
    phosphorus_mg_rni = _standard_field("인 권장섭취량(mg/일)")
    phosphorus_mg_ai = _standard_field("인 충분섭취량(mg/일)")
    phosphorus_mg_ul = _standard_field("인 상한섭취량(mg/일)")
    potassium_mg_rni = _standard_field("칼륨 권장섭취량(mg/일)")
    potassium_mg_ai = _standard_field("칼륨 충분섭취량(mg/일)")
    potassium_mg_ul = _standard_field("칼륨 상한섭취량(mg/일)")
    sodium_mg_rni = _standard_field("나트륨 권장섭취량(mg/일)")
    sodium_mg_ai = _standard_field("나트륨 충분섭취량(mg/일)")
    sodium_mg_ul = _standard_field("나트륨 상한섭취량(mg/일)")
    vitamin_a_ug_rae_rni = _standard_field("비타민 A 권장섭취량(μg RAE/일)")
    vitamin_a_ug_rae_ai = _standard_field("비타민 A 충분섭취량(μg RAE/일)")
    vitamin_a_ug_rae_ul = _standard_field("비타민 A 상한섭취량(μg RAE/일)")
    thiamine_mg_rni = _standard_field("티아민 권장섭취량(mg/일)")
    thiamine_mg_ai = _standard_field("티아민 충분섭취량(mg/일)")
    thiamine_mg_ul = _standard_field("티아민 상한섭취량(mg/일)")
    riboflavin_mg_rni = _standard_field("리보플라빈 권장섭취량(mg/일)")
    riboflavin_mg_ai = _standard_field("리보플라빈 충분섭취량(mg/일)")
    riboflavin_mg_ul = _standard_field("리보플라빈 상한섭취량(mg/일)")
    niacin_mg_rni = _standard_field("나이아신 권장섭취량(mg NE/일)")
    niacin_mg_ai = _standard_field("나이아신 충분섭취량(mg NE/일)")
    niacin_mg_ul = _standard_field("나이아신 상한섭취량(mg NE/일)")
    vitamin_c_mg_rni = _standard_field("비타민 C 권장섭취량(mg/일)")
    vitamin_c_mg_ai = _standard_field("비타민 C 충분섭취량(mg/일)")
    vitamin_c_mg_ul = _standard_field("비타민 C 상한섭취량(mg/일)")
    vitamin_d_ug_rni = _standard_field("비타민 D 권장섭취량(μg/일)")
    vitamin_d_ug_ai = _standard_field("비타민 D 충분섭취량(μg/일)")
    vitamin_d_ug_ul = _standard_field("비타민 D 상한섭취량(μg/일)")

    class Meta:
        table = "nutrient_standard"
        indexes = (("grp", "age"),)


class DisplaySupplementNutrientRank(models.Model):
    id = fields.BigIntField(primary_key=True, description="영양제 랭킹 전시 식별자")
    title = fields.CharField(max_length=100, description="전시 제목")
    start_at = fields.DatetimeField(description="전시 시작 일시")
    end_at = fields.DatetimeField(description="전시 종료 일시")
    is_enabled = fields.BooleanField(default=False, description="관리자 전시 활성화 여부")
    created_by_admin = fields.ForeignKeyField(
        "models.Admin",
        related_name="supplement_rank_displays",
        null=True,
        on_delete=fields.SET_NULL,
        description="전시를 생성한 관리자 식별자",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="전시 생성 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="전시 최종 수정 일시")

    class Meta:
        table = "display_suppl_nutr_rank"
        indexes = (("is_enabled", "start_at", "end_at"), ("created_by_admin",))


class SupplementNutrientRankItem(models.Model):
    id = fields.BigIntField(primary_key=True, description="영양제 랭킹 전시 상품 식별자")
    display = fields.ForeignKeyField(
        "models.DisplaySupplementNutrientRank",
        related_name="items",
        on_delete=fields.CASCADE,
        description="영양제 랭킹 전시 식별자",
    )
    supplement_nutrient = fields.ForeignKeyField(
        "models.SupplementNutrient",
        related_name="rank_items",
        on_delete=fields.RESTRICT,
        description="전시할 건강기능식품 식별자",
    )
    rank_no = fields.IntField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        description="전시 순위. 1부터 5까지 사용",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="전시 상품 생성 일시")

    class Meta:
        table = "suppl_nutr_rank_item"
        unique_together = (
            ("display", "supplement_nutrient"),
            ("display", "rank_no"),
        )


class UserSupplementNutrient(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="supplement_nutrients",
        on_delete=fields.CASCADE,
    )
    supplement_nutrient = fields.ForeignKeyField(
        "models.SupplementNutrient",
        related_name="user_registrations",
        on_delete=fields.RESTRICT,
        null=True,
    )
    custom_name = fields.CharField(max_length=255, null=True)
    dose_amount = fields.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    dose_unit = fields.CharField(max_length=20)
    start_date = fields.DateField()
    end_date = fields.DateField(null=True)
    status = fields.CharEnumField(SupplementStatus, default=SupplementStatus.ACTIVE)
    note = fields.CharField(max_length=500, null=True)
    review_body = fields.CharField(
        max_length=500,
        null=True,
        description="다른 사용자에게 공개되는 후기 본문",
    )
    score = fields.IntField(
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        description="사용자가 남긴 별점 1~5",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "user_suppl_nutrient"
        unique_together = (("user", "supplement_nutrient"),)
        indexes = (("user", "status"),)


class SupplementReviewReport(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="supplement_review_reports",
        on_delete=fields.CASCADE,
    )
    registration = fields.ForeignKeyField(
        "models.UserSupplementNutrient",
        related_name="reports",
        on_delete=fields.CASCADE,
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "supplement_review_report"
        unique_together = (("user", "registration"),)
        indexes = (("registration",),)


class UserSupplementNutrientSlot(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_suppl_nutrient = fields.ForeignKeyField(
        "models.UserSupplementNutrient",
        related_name="slots",
        on_delete=fields.CASCADE,
    )
    slot = fields.CharEnumField(MealSlot)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_suppl_nutrient_slots"
        unique_together = (("user_suppl_nutrient", "slot"),)


class SupplementDose(models.Model):
    """One taken dose per registered supplement, calendar day and meal slot."""

    id = fields.BigIntField(primary_key=True)
    registration = fields.ForeignKeyField(
        "models.UserSupplementNutrient", related_name="doses", on_delete=fields.CASCADE,
    )
    dose_date = fields.DateField()
    slot = fields.CharEnumField(MealSlot)
    taken_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "supplement_doses"
        unique_together = (("registration", "dose_date", "slot"),)
