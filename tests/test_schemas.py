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


def test_article_schema_limits_search_snippets_without_cutting_words():
    article = Article.model_validate(
        {
            "title": (
                "В Мариуполе жильцы многоквартирного дома рассказали о продолжительной "
                "неисправности лифта и возникших сложностях"
            ),
            "slug": "lift-v-mariupole",
            "lead": "Жильцы дома в Мариуполе сообщили о продолжительной неисправности лифта.",
            "sections": [
                {
                    "heading": "",
                    "paragraphs": [
                        "По словам автора сообщения, оборудование требует проверки."
                    ],
                }
            ],
            "facts": [],
            "quote": None,
            "source_note": "",
            "excerpt": (
                "Жильцы одного из домов Мариуполя рассказали о неисправности лифта "
                "и сложностях, с которыми они сталкиваются каждый день."
            ),
            "seo_title": (
                "В Мариуполе жильцы дома сообщили о продолжительной неисправности лифта"
            ),
            "seo_description": (
                "Жильцы многоквартирного дома в Мариуполе сообщили, что лифт долгое "
                "время не работает. Рассказываем, что известно и куда они обращались "
                "для решения проблемы."
            ),
            "focus_keyword": "не работает лифт в Мариуполе",
            "tags": ["Мариуполь", "ЖКХ"],
            "image_alt": "Лифт в многоквартирном доме Мариуполя",
            "uncertainties": ["Нет официального комментария обслуживающей организации."],
            "editor_notes": ["Утверждение о сроке неисправности требует проверки."],
        }
    )

    assert len(article.title) <= 80
    assert len(article.seo_title) <= 60
    assert len(article.seo_description) <= 160
    assert not article.title.endswith((" ", ",", ":", "—", "-"))
    assert not article.seo_title.endswith((" ", ",", ":", "—", "-"))
