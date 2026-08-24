from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MinValueValidator

from app.models.enums import MealSlot, SupplementStatus


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
    )
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
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "user_suppl_nutrient"
        unique_together = (("user", "supplement_nutrient"),)
        indexes = (("user", "status"),)


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
