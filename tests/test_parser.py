from app.commands.parser import parse_command


def test_parse_command_basic():
    cmd = parse_command("/help")
    assert cmd is not None
    assert cmd.name == "help"
    assert cmd.args == []


def test_parse_command_with_args():
    cmd = parse_command("/status user1")
    assert cmd is not None
    assert cmd.name == "status"
    assert cmd.args == ["user1"]


def test_parse_command_bot_mention():
    cmd = parse_command("/status@mybot user1")
    assert cmd is not None
    assert cmd.name == "status"


def test_parse_command_non_command():
    assert parse_command("hello") is None
