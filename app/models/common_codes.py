from tortoise import fields, models


class CommonCodeGroup(models.Model):
    id = fields.BigIntField(primary_key=True, description="공통코드 그룹 식별자")
    category = fields.CharField(max_length=20, description="공통코드 대분류")
    group_code = fields.CharField(max_length=20, unique=True, description="코드그룹")
    group_name = fields.CharField(max_length=20, description="코드그룹명")
    description = fields.CharField(max_length=200, null=True, description="코드그룹 설명")
    is_active = fields.BooleanField(default=True, description="사용 여부")
    created_by_admin: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Admin",
        related_name="created_common_code_groups",
        null=True,
        on_delete=fields.SET_NULL,
        description="생성 관리자 식별자",
    )
    updated_by_admin: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Admin",
        related_name="updated_common_code_groups",
        null=True,
        on_delete=fields.SET_NULL,
        description="수정 관리자 식별자",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="생성 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="수정 일시")

    codes: fields.ReverseRelation["CommonCode"]

    class Meta:
        table = "common_code_groups"
        indexes = (
            ("category", "is_active", "group_code"),
            ("created_by_admin",),
            ("updated_by_admin",),
        )


class CommonCode(models.Model):
    id = fields.BigIntField(primary_key=True, description="공통코드 식별자")
    group: fields.ForeignKeyRelation[CommonCodeGroup] = fields.ForeignKeyField(
        "models.CommonCodeGroup",
        related_name="codes",
        on_delete=fields.CASCADE,
        description="공통코드 그룹 식별자",
    )
    detail_code = fields.CharField(max_length=20, description="상세코드")
    detail_name = fields.CharField(max_length=20, description="상세코드명")
    description = fields.CharField(max_length=200, null=True, description="상세코드 설명")
    sort_order = fields.IntField(default=0, description="정렬순서")
    is_active = fields.BooleanField(default=True, description="사용 여부")
    created_by_admin: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Admin",
        related_name="created_common_codes",
        null=True,
        on_delete=fields.SET_NULL,
        description="생성 관리자 식별자",
    )
    updated_by_admin: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Admin",
        related_name="updated_common_codes",
        null=True,
        on_delete=fields.SET_NULL,
        description="수정 관리자 식별자",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="생성 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="수정 일시")

    class Meta:
        table = "common_codes"
        unique_together = (("group", "detail_code"),)
        indexes = (
            ("group", "is_active", "sort_order"),
            ("created_by_admin",),
            ("updated_by_admin",),
        )
