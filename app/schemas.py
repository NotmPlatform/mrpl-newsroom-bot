import re

from pydantic import BaseModel, Field, field_validator, model_validator


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _shorten(value: str, limit: int, *, ellipsis: bool = False) -> str:
    value = _clean(value)
    if len(value) <= limit:
        return value
    suffix = "…" if ellipsis else ""
    room = limit - len(suffix)
    shortened = value[: room + 1]
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    shortened = shortened[:room].rstrip(" ,;:–—-")
    return shortened + suffix


class ArticleSection(BaseModel):
    heading: str = Field(default="", max_length=140)
    paragraphs: list[str] = Field(min_length=1, max_length=8)

    @field_validator("heading")
    @classmethod
    def clean_heading(cls, value: str) -> str:
        return _clean(value)

    @field_validator("paragraphs")
    @classmethod
    def clean_paragraphs(cls, values: list[str]) -> list[str]:
        result = [_clean(item)[:2500] for item in values if _clean(item)]
        if not result:
            raise ValueError("A section must contain text")
        return result


class ArticleQuote(BaseModel):
    text: str = Field(max_length=1000)
    author: str = Field(default="", max_length=160)

    @field_validator("text", "author")
    @classmethod
    def clean_fields(cls, value: str) -> str:
        return _clean(value)


class Article(BaseModel):
    title: str = Field(min_length=10, max_length=80)
    slug: str = Field(default="", max_length=180)
    lead: str = Field(min_length=20, max_length=1200)
    sections: list[ArticleSection] = Field(min_length=1, max_length=8)
    facts: list[str] = Field(default_factory=list, max_length=10)
    quote: ArticleQuote | None = None
    source_note: str = Field(default="", max_length=600)
    excerpt: str = Field(min_length=20, max_length=240)
    seo_title: str = Field(min_length=10, max_length=60)
    seo_description: str = Field(min_length=60, max_length=160)
    focus_keyword: str = Field(default="новости Мариуполя", max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=8)
    image_alt: str = Field(default="Новости Мариуполя", max_length=220)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    editor_notes: list[str] = Field(default_factory=list, max_length=8)

    @field_validator(
        "title",
        "slug",
        "lead",
        "source_note",
        "excerpt",
        "seo_title",
        "seo_description",
        "focus_keyword",
        "image_alt",
    )
    @classmethod
    def clean_strings(cls, value: str) -> str:
        return _clean(value)

    @field_validator("title", mode="before")
    @classmethod
    def limit_title(cls, value: str) -> str:
        return _shorten(value, 80)

    @field_validator("excerpt", mode="before")
    @classmethod
    def limit_excerpt(cls, value: str) -> str:
        return _shorten(value, 240, ellipsis=True)

    @field_validator("seo_title", mode="before")
    @classmethod
    def limit_seo_title(cls, value: str) -> str:
        return _shorten(value, 60)

    @field_validator("seo_description", mode="before")
    @classmethod
    def limit_seo_description(cls, value: str) -> str:
        return _shorten(value, 160, ellipsis=True)

    @field_validator("facts", "tags", "uncertainties", "editor_notes")
    @classmethod
    def clean_lists(cls, values: list[str]) -> list[str]:
        return [_clean(value)[:500] for value in values if _clean(value)]

    @model_validator(mode="after")
    def quote_requires_text(self) -> "Article":
        if self.quote and not self.quote.text:
            self.quote = None
        return self
