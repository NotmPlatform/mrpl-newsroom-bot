from app.schemas import Article
from app.keyboards import (
    collecting_keyboard,
    editor_preview_keyboard,
    editor_review_keyboard,
    volunteer_preview_keyboard,
)


def test_article_schema_accepts_valid_news():
    article = Article.model_validate(
        {
            "title": "В Мариуполе открылась новая городская площадка",
            "slug": "novaya-gorodskaya-ploschadka",
            "lead": "В центре Мариуполя открылась новая площадка для жителей города.",
            "sections": [
                {
                    "heading": "Что известно",
                    "paragraphs": [
                        "Площадка начала работать сегодня. Дополнительные сведения уточняются."
                    ],
                }
            ],
            "facts": ["Открытие состоялось в Мариуполе"],
            "quote": None,
            "source_note": "Информация предоставлена автором сообщения.",
            "excerpt": "В Мариуполе начала работать новая городская площадка.",
            "seo_title": "В Мариуполе открылась новая городская площадка",
            "seo_description": (
                "В центре Мариуполя открылась новая городская площадка. "
                "Рассказываем, что известно на данный момент."
            ),
            "focus_keyword": "новости Мариуполя",
            "tags": ["Мариуполь", "город"],
            "image_alt": "Новая городская площадка в Мариуполе",
            "uncertainties": [],
            "editor_notes": [],
        }
    )
    assert article.title.startswith("В Мариуполе")


def test_callback_data_fits_telegram_limit():
    submission_id = "f" * 32
    keyboards = [
        collecting_keyboard(submission_id),
        volunteer_preview_keyboard(submission_id),
        editor_preview_keyboard(submission_id, "https://mrpl.ru/wp-admin/post.php?post=1"),
        editor_review_keyboard(submission_id, "https://mrpl.ru/wp-admin/post.php?post=1"),
    ]
    for keyboard in keyboards:
        for row in keyboard.inline_keyboard:
            for button in row:
                if button.callback_data:
                    assert len(button.callback_data.encode("utf-8")) <= 64
