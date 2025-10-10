import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

from utils.types import SHA256B64


class ContextSchema(BaseModel):
    digest: SHA256B64 = Field(..., description='The SHA256B64 hash of the document')
    collection_name: str = Field(..., description='The name of the collection')
    tenant_id: UUID = Field(..., description='The tenant ID')


class MetadataSchema(BaseModel):
    document_type: str | None = Field(default=None, description='The type of document, e.g. Annual Report')
    company_name: str | None = Field(default=None, description='The name of the company')
    parent_company: str | None = Field(default=None, description='The parent company of the company')
    ultimate_parent_company: str | None = Field(default=None, description='The ultimate parent company of the company')
    reporting_date: datetime.date | None = Field(default=None, description='The date the report was generated')
    reporting_year: int | None = Field(default=None, description='The reporting year, e.g. 2022')
    call_date: datetime.date | None = Field(default=None, description='The date the document was received')
    company_register: str | None = Field(
        default=None, description='The company register where the document was received'
    )
    register_number: str | None = Field(default=None, description="The company's register number")
    tags: List[str] | None = Field(default=None, description='Tags for the document')
