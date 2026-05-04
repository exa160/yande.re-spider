"""
高级搜索类 - 支持 yande.re API 高级搜索语法

搜索语法:
    +keyword     包含该内容
    -keyword     排除该内容
    {field}:{op}{value}  字段比较
        例如: width:>=1000, height:>=1000, score:>=n
        ext:png, rating:e

多个条件用空格或 + 连接

示例:
    rating:e width:>=1000 height:>=1000 ext:png -explicit_tag +safe_tag
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Any


class SearchOperator(Enum):
    EQ = "="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="


class SearchRating(Enum):
    SAFE = "s"
    QUESTIONABLE = "q"
    EXPLICIT = "e"


SUPPORTED_FIELDS = {
    "width": {"type": int, "operators": ["=", ">=", "<=", ">", "<"]},
    "height": {"type": int, "operators": ["=", ">=", "<=", ">", "<"]},
    "score": {"type": int, "operators": ["=", ">=", "<=", ">", "<"]},
    "mpixels": {"type": float, "operators": ["=", ">=", "<=", ">", "<"]},
    "filesize": {"type": int, "operators": ["=", ">=", "<=", ">", "<"]},
    "date": {"type": str, "operators": ["="]},
    "id": {"type": int, "operators": ["=", ">=", "<=", ">", "<"]},
    "pixels": {"type": int, "operators": ["=", ">=", "<=", ">", "<"]},
    "ext": {
        "type": str,
        "operators": ["="],
        "values": ["jpg", "jpeg", "png", "gif", "webp"],
    },
    "rating": {
        "type": str,
        "operators": ["="],
        "values": ["s", "q", "e", "safe", "questionable", "explicit"],
    },
    "source": {"type": str, "operators": ["="]},
    "parent": {"type": int, "operators": ["="]},
    "status": {
        "type": str,
        "operators": ["="],
        "values": ["any", "active", "deleted", "flagged", "pending", "spam"],
    },
}


@dataclass
class SearchCondition:
    field: str
    operator: SearchOperator
    value: Any
    exclude: bool = False


@dataclass
class TagCondition:
    tag: str
    exclude: bool = False


class AdvancedSearch:
    def __init__(self):
        self.tags: List[TagCondition] = []
        self.conditions: List[SearchCondition] = []

    def add_tag(self, tag: str, exclude: bool = False) -> "AdvancedSearch":
        if tag:
            self.tags.append(TagCondition(tag=tag.strip(), exclude=exclude))
        return self

    def add_condition(
        self, field: str, operator: SearchOperator, value: Any, exclude: bool = False
    ) -> "AdvancedSearch":
        if field and field in SUPPORTED_FIELDS:
            self.conditions.append(
                SearchCondition(
                    field=field, operator=operator, value=value, exclude=exclude
                )
            )
        return self

    def add_rating(self, rating: str) -> "AdvancedSearch":
        rating_map = {
            "s": "s",
            "safe": "s",
            "q": "q",
            "questionable": "q",
            "e": "e",
            "explicit": "e",
            "S": "s",
            "Q": "q",
            "E": "e",
            "Safe": "s",
            "Questionable": "q",
            "Explicit": "e",
        }
        mapped = rating_map.get(rating, rating)
        if mapped:
            self.add_condition("rating", SearchOperator.EQ, mapped)
        return self

    def add_ext(self, ext: str) -> "AdvancedSearch":
        if ext:
            self.add_condition("ext", SearchOperator.EQ, ext.lower())
        return self

    def add_width(self, operator: str, value: int) -> "AdvancedSearch":
        op = SearchOperator(operator) if isinstance(operator, str) else operator
        self.add_condition("width", op, value)
        return self

    def add_height(self, operator: str, value: int) -> "AdvancedSearch":
        op = SearchOperator(operator) if isinstance(operator, str) else operator
        self.add_condition("height", op, value)
        return self

    def add_score(self, operator: str, value: int) -> "AdvancedSearch":
        op = SearchOperator(operator) if isinstance(operator, str) else operator
        self.add_condition("score", op, value)
        return self

    def to_api_string(self) -> str:
        parts = []

        for tag_cond in self.tags:
            prefix = "-" if tag_cond.exclude else ""
            clean_tag = tag_cond.tag.lstrip("+-~")
            if clean_tag:
                parts.append(f"{prefix}{clean_tag}")

        for cond in self.conditions:
            op_str = cond.operator.value if cond.operator != SearchOperator.EQ else ""
            if cond.exclude:
                parts.append(f"-{cond.field}:{op_str}{cond.value}")
            else:
                parts.append(f"{cond.field}:{op_str}{cond.value}")

        return " ".join(parts)

    @staticmethod
    def parse(search_string: str) -> "AdvancedSearch":
        search = AdvancedSearch()
        if not search_string:
            return search

        tokens = search_string.split()

        for token in tokens:
            if not token:
                continue

            if token.startswith("-"):
                exclude = True
                token = token[1:]
            else:
                exclude = False

            if ":" in token:
                field, value = token.split(":", 1)
                field = field.lstrip("-")

                if field not in SUPPORTED_FIELDS:
                    search.add_tag(token, exclude)
                    continue

                op_match = re.match(r"^([><=!]+)(.+)$", value)
                if op_match:
                    op_str, val_str = op_match.groups()
                    if op_str == "=":
                        operator = SearchOperator.EQ
                    elif op_str == ">=":
                        operator = SearchOperator.GE
                    elif op_str == "<=":
                        operator = SearchOperator.LE
                    elif op_str == ">":
                        operator = SearchOperator.GT
                    elif op_str == "<":
                        operator = SearchOperator.LT
                    elif op_str == "!=":
                        operator = SearchOperator.NE
                    else:
                        operator = SearchOperator.EQ

                    field_info = SUPPORTED_FIELDS.get(field, {})
                    val_type = field_info.get("type", str)

                    try:
                        if val_type == int:
                            value = int(val_str)
                        elif val_type == float:
                            value = float(val_str)
                        else:
                            value = val_str

                        search.add_condition(field, operator, value, exclude)
                    except ValueError:
                        search.add_tag(token, exclude)
                else:
                    search.add_condition(field, SearchOperator.EQ, value, exclude)
            else:
                search.add_tag(token, exclude)

        return search

    def clear(self) -> "AdvancedSearch":
        self.tags = []
        self.conditions = []
        return self


def build_search_string(
    tags: str = "",
    author: Optional[str] = None,
    min_width: Optional[int] = None,
    max_width: Optional[int] = None,
    min_height: Optional[int] = None,
    max_height: Optional[int] = None,
    rating: Optional[str] = None,
    min_score: Optional[int] = None,
    file_type: Optional[str] = None,
    min_file_size: Optional[int] = None,
    max_file_size: Optional[int] = None,
) -> str:
    search = AdvancedSearch()

    if tags:
        for tag in tags.split():
            tag = tag.strip()
            if tag.startswith("-"):
                search.add_tag(tag[1:], exclude=True)
            else:
                search.add_tag(tag)

    if author:
        search.add_tag(f"author:{author}")

    if rating and rating != "All":
        search.add_rating(rating)

    if file_type:
        search.add_ext(file_type)

    if min_width is not None:
        search.add_width(SearchOperator.GE, min_width)

    if max_width is not None:
        search.add_width(SearchOperator.LE, max_width)

    if min_height is not None:
        search.add_height(SearchOperator.GE, min_height)

    if max_height is not None:
        search.add_height(SearchOperator.LE, max_height)

    if min_score is not None:
        search.add_score(SearchOperator.GE, min_score)

    if min_file_size is not None:
        search.add_condition("filesize", SearchOperator.GE, min_file_size * 1024)

    if max_file_size is not None:
        search.add_condition("filesize", SearchOperator.LE, max_file_size * 1024)

    return search.to_api_string()


if __name__ == "__main__":
    search = AdvancedSearch()
    search.add_tag("anime")
    search.add_tag("character", exclude=True)
    search.add_rating("e")
    search.add_width(SearchOperator.GE, 1000)
    search.add_height(SearchOperator.GE, 1000)
    search.add_ext("png")

    print(search.to_api_string())
    print(
        AdvancedSearch.parse(
            "rating:e width:>=1000 height:>=1000 ext:png -explicit_tag"
        ).to_api_string()
    )
