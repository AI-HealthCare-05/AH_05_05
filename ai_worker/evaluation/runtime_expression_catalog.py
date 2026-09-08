from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.repositories.medication_expression_catalog_repository import (
    DbMedicationExpressionCatalog,
)
from ai_worker.repositories.supplement_ingredient_catalog_repository import (
    CompositeSupplementIngredientCatalog,
    DbSupplementIngredientCatalog,
    QdrantSupplementIngredientCatalog,
)


def build_runtime_expression_catalog(
    *,
    settings: Config,
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    dataset_version: str,
) -> DbMedicationExpressionCatalog:
    """평가 대상 릴리스와 동일한 typed 질문 해석 카탈로그를 만든다."""

    supplement_catalog = CompositeSupplementIngredientCatalog(
        sources=[
            DbSupplementIngredientCatalog(),
            QdrantSupplementIngredientCatalog(
                client=qdrant_client,
                collection_name=collection_name,
                dataset_version=dataset_version,
            ),
        ]
    )
    return DbMedicationExpressionCatalog(
        supplement_catalog=supplement_catalog,
    )
