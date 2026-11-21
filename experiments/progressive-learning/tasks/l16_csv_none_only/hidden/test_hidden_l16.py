import ast
import inspect

from minitext import csvlite
from minitext.csvlite import format_line, parse_line

PARSE = '''def parse_line(line):
    return line.rstrip("\\n").split(",")
'''


def test_none_is_empty():
    assert format_line([None, "a", None]) == ",a,"
    assert format_line([None]) == ""


def test_everything_else_unchanged():
    assert format_line([0, False, "", 1.5]) == "0,False,,1.5"
    assert format_line(["a,b", 'q"t', " sp "]) == 'a,b,q"t, sp '


def test_parse_line_untouched():
    tree = ast.parse(inspect.getsource(csvlite.parse_line))
    tree.body[0].body = [n for n in tree.body[0].body
                         if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    assert ast.dump(tree) == ast.dump(ast.parse(PARSE))
    assert parse_line('"x,y",z\n') == ['"x', 'y"', "z"]
