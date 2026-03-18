from app.domain.models.message import Message


def test_message_accepts_string_attachments() -> None:
    message = Message.model_validate(
        {
            "message": "done",
            "attachments": [
                "/home/ubuntu/extract_schedule.js",
                "/home/ubuntu/work_hours_summary.json",
            ],
        }
    )

    assert [attachment.filepath for attachment in message.attachments] == [
        "/home/ubuntu/extract_schedule.js",
        "/home/ubuntu/work_hours_summary.json",
    ]
    assert [attachment.filename for attachment in message.attachments] == [
        "extract_schedule.js",
        "work_hours_summary.json",
    ]
