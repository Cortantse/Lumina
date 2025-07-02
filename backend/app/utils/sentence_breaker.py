from typing import Tuple


def _is_decimal_point(sentence: str, pos: int) -> bool:
    """检查当前位置的点是否是小数点"""
    if pos <= 0 or pos >= len(sentence) - 1:
        return False

    prev_char = sentence[pos-1]
    next_char = sentence[pos+1]
    return prev_char.isdigit() and next_char.isdigit()


def _is_abbreviation_period(sentence: str, pos: int) -> bool:
    """检查当前位置的点是否是缩写词中的点"""
    if pos <= 0 or pos >= len(sentence) - 1:
        return False

    prev_char = sentence[pos-1]
    next_char = sentence[pos+1]
    return prev_char.isalpha() and next_char.isalpha() and not next_char.isspace()


def _check_ellipsis(sentence: str, pos: int) -> Tuple[bool, int]:
    """检查是否是省略号，返回(是否是省略号, 省略号长度)"""
    if pos + 2 < len(sentence) and sentence[pos:pos+3] == '...':
        return True, 3
    return False, 0


def _find_sentence_break(current_sentence: str, end_mark: str) -> Tuple[bool, str, str]:
    """
    在句子中查找分隔标记，并分割句子
    返回: (是否找到分隔标记, 完整句子部分, 剩余部分)
    """
    if end_mark not in current_sentence:
        return False, "", ""

    end_pos = current_sentence.find(end_mark)

    # 特殊情况处理
    if end_mark == '.':
        # 处理小数点
        if _is_decimal_point(current_sentence, end_pos):
            remaining = current_sentence[end_pos+1:]
            return _find_sentence_break(remaining, end_mark)

        # 处理缩写词中的点
        if _is_abbreviation_period(current_sentence, end_pos):
            remaining = current_sentence[end_pos+1:]
            return _find_sentence_break(remaining, end_mark)

        # 处理省略号
        is_ellipsis, ellipsis_len = _check_ellipsis(current_sentence, end_pos)
        if is_ellipsis:
            complete = current_sentence[:end_pos+ellipsis_len]
            remaining = current_sentence[end_pos+ellipsis_len:]
            return True, complete, remaining

    # 处理常规句末标记
    complete = current_sentence[:end_pos+len(end_mark)]
    remaining = current_sentence[end_pos+len(end_mark):]

    return True, complete, remaining


def _process_long_sentence(current_sentence: str) -> Tuple[bool, str, str]:
    """
    处理长句，按照分隔符分割
    返回: (是否需要分割, 分割的句子, 剩余部分)
    """
    if len(current_sentence) <= 100:
        return False, "", ""

    # 查找适合断句的位置
    break_positions = []
    for mark in ['，', '；', '、', ',', ';']:
        pos = current_sentence.rfind(mark)
        if pos > 30:  # 至少要有30个字符才考虑断句
            break_positions.append(pos)

    if not break_positions:
        return False, "", ""

    # 找到最靠后的分隔符
    pos = max(break_positions)
    complete_sentence = current_sentence[:pos+1]
    remaining = current_sentence[pos+1:]

    return True, complete_sentence, remaining