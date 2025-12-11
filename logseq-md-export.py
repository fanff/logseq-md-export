#!/usr/bin/env python3
import re
import os
import shutil
from enum import Enum
import argparse
from typing import Dict, List
import logging


logger = logging.getLogger("logseq-md-export")


class LineType(Enum):
    TITLE = 1
    LIST = 2
    QUOTE = 3
    CODE_BLOCK_MARKER = 4
    CODE = 5
    EMPTY = 6
    TEXT = 7


class LineHierarchy(Enum):
    PARENT = 1
    CHILD = 2


def get_file_info(file_path):
    abs_path = os.path.abspath(file_path)
    os.path.basename(abs_path)


def import_asset(logseq_file_base_dir, filename, output_project_path, subdir=""):

    os.makedirs(os.path.join(output_project_path, "assets"), exist_ok=True)
    shutil.copy(
        os.path.join(logseq_file_base_dir, "..", "assets", subdir, filename),
        os.path.join(output_project_path, "assets", filename),
    )


def get_line_type(line, line_content_raw):
    L1_tag = line_content_raw[0]
    L2_tag = line_content_raw[2] if len(line_content_raw) > 2 else None

    if L1_tag == "#":
        return LineType.TITLE, LineHierarchy.PARENT

    if L2_tag is None:
        if L1_tag == "-":
            # empty line on a list
            return LineType.EMPTY, LineHierarchy.PARENT
        elif L1_tag == " ":
            # empty line on a multi-line block
            return LineType.EMPTY, LineHierarchy.CHILD
        else:
            logger.error("PARSING ERROR AT LINE: %s", line)
            exit(1)
    if L2_tag == " ":
        # this must be part of a multi-line content block
        return LineType.TEXT, LineHierarchy.CHILD
    elif L2_tag == ">":
        if L1_tag == "-":
            return LineType.QUOTE, LineHierarchy.PARENT
        else:
            return LineType.QUOTE, LineHierarchy.CHILD
    elif L2_tag == "#":
        # titles an only be parent. If this is not, it's not a title!
        if L1_tag == "-":
            return LineType.TITLE, LineHierarchy.PARENT
        elif L1_tag == " ":
            return LineType.TEXT, LineHierarchy.CHILD
        else:
            logger.error("PARSING ERROR AT LINE: %s", line)
            exit(1)
    elif L2_tag == "`":
        parent_code_block = re.search("^(\t*)- (```)", line)
        child_code_block = re.search("^(\t*)  (```)", line)
        if parent_code_block is not None:
            return LineType.CODE_BLOCK_MARKER, LineHierarchy.PARENT
        if child_code_block is not None:
            return LineType.CODE_BLOCK_MARKER, LineHierarchy.CHILD
        # if no code block detected, could just be a line starting with "`"
        if L1_tag == "-":
            return LineType.LIST, LineHierarchy.PARENT
        elif L1_tag == " ":
            return LineType.TEXT, LineHierarchy.CHILD
        else:
            logger.error("PARSING ERROR AT LINE: %s", line)
            exit(1)
    else:
        # no tag recognized, must be text.
        if L1_tag == "-":
            return LineType.LIST, LineHierarchy.PARENT
        # no L1_tag, must be part of a multi-line content
        else:
            return LineType.TEXT, LineHierarchy.CHILD


def export_file_to_folder(logseq_file: str, output_path: str, no_br: bool = False):
    """
    This is the main entry point to export a Logseq markdown file to a folder.
    Args:
        logseq_file (str): Path to the Logseq markdown file to export.
        output_path (str): Path to the output directory.
        no_br (bool): If True, do not insert <br> tags for empty lines.

    Returns:
        None
    """

    logseq_file_base_dir = os.path.dirname(os.path.abspath(logseq_file))

    os.makedirs(output_path, exist_ok=True)

    # Open logseq page and read it
    with open(logseq_file, "r", encoding="utf-8") as file:
        lines_raw = file.readlines()

    # define variables to keep track of indentation levels
    target_line_indent = 0
    cur_list_depth = 0
    last_target_line_indent = 0
    traversing_code_block = False
    lines_to_skip = 0

    # will contain dicts parsed line info
    lines: List[Dict] = []

    for line in lines_raw:
        # match any line and get its indentation level
        line_re = re.search("^(\t*)(.*)$", line)

        if line_re is None:
            logger.warning("Warning: no match on: %s", line)
            logger.warning("Skipping the line")
            continue

        line_content_raw = line_re.groups()[1]
        line_indent = len(line_re.groups()[0])
        line_type, line_hierarchy = get_line_type(line, line_content_raw)

        lines.append(
            {
                "content": line_content_raw,
                "indent": line_indent,
                "type": line_type,
                "hierarchy": line_hierarchy,
            }
        )

    content = ""  # make sure content is always at least defined
    output_content = ""
    for i, line_info in enumerate(lines):

        if lines_to_skip > 0:
            lines_to_skip -= 1
            continue

        logger.debug(
            "[%d %s %s] : %s",
            i,
            line_info["type"],
            line_info["hierarchy"],
            line_info["content"],
        )

        if line_info["type"] == LineType.CODE_BLOCK_MARKER:
            traversing_code_block = not traversing_code_block
        elif line_info["content"].find("../assets") >= 0:
            asset_re = re.search(
                r"(^.*\[.*\]\()(../)assets/(.*)\)", line_info["content"]
            )
            if asset_re is not None:
                filename = asset_re.groups()[2]
                logger.debug("Importing asset: %s", filename)
                import_asset(
                    logseq_file_base_dir,
                    filename,
                    output_path,
                )
                line_info["content"] = (
                    asset_re.groups()[0] + "assets/" + asset_re.groups()[2] + ")"
                )

                # TODO make sure this need not to be handled down below as well.
        elif line_info["content"].find("{{renderer :drawio,") >= 0:
            asset_re = re.search(
                r"(^.*){{renderer :drawio, (.*.svg)}}", line_info["content"]
            )
            if asset_re is not None:
                filename = asset_re.groups()[1]
                logger.debug("filename: %s", filename)
                logger.debug("Importing asset: %s", filename)
                import_asset(
                    logseq_file_base_dir,
                    filename,
                    output_path,
                    subdir=os.path.join("storages", "logseq-drawio-plugin"),
                )
                line_info["content"] = (
                    asset_re.groups()[0]
                    + "!["
                    + filename
                    + "]"
                    + "(assets/"
                    + filename
                    + ")"
                )
                # TODO make sure this need not to be handled down below as well.
        elif line_info["content"].find("- TODO ") >= 0:
            checkbox_re = re.search(r"(^\t*)- TODO (.*)$", line_info["content"])
            if checkbox_re is not None:
                line_info["content"] = (
                    checkbox_re.groups()[0]
                    + "- **&#x2610;"
                    + " TODO** "
                    + checkbox_re.groups()[1]
                )
        elif line_info["content"].find("- DOING ") >= 0:
            checkbox_re = re.search(r"(^\t*)- DOING (.*)$", line_info["content"])
            if checkbox_re is not None:
                line_info["content"] = (
                    checkbox_re.groups()[0]
                    + "- **&#x231B;"
                    + " DOING** "
                    + checkbox_re.groups()[1]
                )
        elif line_info["content"].find("- DONE ") >= 0:
            checkbox_re = re.search(r"(^\t*)- DONE (.*)$", line_info["content"])
            if checkbox_re is not None:
                line_info["content"] = (
                    checkbox_re.groups()[0]
                    + "- **&#x2611;** ~~"
                    + checkbox_re.groups()[1]
                    + "~~"
                )
        elif line_info["content"].find("- LATER ") >= 0:
            checkbox_re = re.search(r"(^\t*)- LATER (.*)$", line_info["content"])
            if checkbox_re is not None:
                line_info["content"] = (
                    checkbox_re.groups()[0]
                    + "- **&#x23F2;"
                    + " LATER** "
                    + checkbox_re.groups()[1]
                )
        elif line_info["content"].find("- NOW ") >= 0:
            checkbox_re = re.search(r"(^\t*)- NOW (.*)$", line_info["content"])
            if checkbox_re is not None:
                line_info["content"] = (
                    checkbox_re.groups()[0]
                    + "- **&#x23F0;"
                    + " NOW** "
                    + checkbox_re.groups()[1]
                )

        # CALCULATE TARGET INDENTATION
        if i == 0:
            target_line_indent = 0
        elif (
            line_info["type"] == LineType.TITLE
            or lines[i - 1]["type"] == LineType.TITLE
        ):
            # Titles have no indentation.
            # Any element that comes immediately after a title must have no indentation as well
            target_line_indent = 0

        if (
            line_info["type"] != LineType.TITLE
            and lines[i - 1]["type"] != LineType.TITLE
        ):
            # If this row belongs to a series of rows of the same kind...
            if line_info["indent"] > lines[i - 1]["indent"]:
                # Standard markdown list: the first level is not indented, the subsequents are.
                cur_list_depth += 1
                if cur_list_depth > 1:
                    target_line_indent = last_target_line_indent + 1
                else:
                    target_line_indent = last_target_line_indent
            elif line_info["indent"] < lines[i - 1]["indent"]:
                # Detect if this LIST element is less indendeted than the previous
                target_line_indent = max(
                    0,
                    last_target_line_indent
                    - (lines[i - 1]["indent"] - line_info["indent"]),
                )
                cur_list_depth -= 1
            else:
                target_line_indent = last_target_line_indent

        if traversing_code_block:
            content = line_info["content"][2:]
        else:
            # Represent each line depending on its type
            if line_info["type"] == LineType.TITLE:
                content = line_info["content"][line_info["content"].find("#") :]
                cur_list_depth = 0
            elif line_info["type"] == LineType.LIST:
                if cur_list_depth > 0:
                    content = line_info["content"]
                    if (
                        i < len(lines) - 1
                        and lines[i + 1]["indent"] < line_info["indent"]
                    ):
                        content = content + "\n"
                else:
                    if (
                        i < len(lines) - 1
                        and lines[i + 1]["type"] == LineType.LIST
                        and lines[i + 1]["indent"] == line_info["indent"]
                    ):
                        content = line_info["content"][2:] + "\\"
                    else:
                        content = line_info["content"][2:]
            elif line_info["type"] == LineType.TEXT:
                if line_info["content"].find("collapsed:: true") >= 0:
                    logger.debug(
                        "Removing logseq-specifc tag: %s", line_info["content"]
                    )
                    continue
                if line_info["content"].find(":LOGBOOK:") >= 0:
                    logger.debug(
                        "Removing logseq-specifc tag and all subsequent entries: %s",
                        line_info["content"],
                    )
                    for l in range(i, len(lines)):
                        if lines[l]["content"].find(":END:") >= 0:
                            break
                        lines_to_skip += 1
                    continue
                else:
                    # We might be in a multi-line content block of some kind.
                    content = line_info["content"][2:]
                # always terminate the line with a return
                if i < len(lines) - 1 and lines[i + 1]["type"] != line_info["type"]:
                    content = content + "\n"
            elif line_info["type"] == LineType.CODE:
                content = line_info["content"][2:]
            elif line_info["type"] == LineType.EMPTY:
                content = "<br>\n" if not no_br else "\n"
            elif line_info["type"] == LineType.CODE_BLOCK_MARKER:
                content = line_info["content"][2:]
            elif line_info["type"] == LineType.QUOTE:
                content = line_info["content"][2:]

            if line_info["type"] != LineType.CODE_BLOCK_MARKER:
                if (
                    i < len(lines) - 1
                    and lines[i + 1]["type"] == LineType.TEXT
                    and not line_info["type"] == LineType.TITLE
                ):
                    content = content + "\\"

        content = content + "\n"

        tabs = "".join(["\t" for _ in range(target_line_indent)])
        content = tabs + content

        output_content += content
        # only update previous element type for next cycle when a new element starts
        if line_info["hierarchy"] == LineHierarchy.PARENT:
            last_target_line_indent = target_line_indent

        # logger.debug("last_target_line_indent: %d, target_line_indent: %d", last_target_line_indent, target_line_indent)
        # logger.debug("cur_list_depth: %d", cur_list_depth)

    # first prepare the output to receive the file.
    final_destination_path = os.path.join(output_path, os.path.basename(logseq_file))

    # finally write the file
    with open(
        final_destination_path,
        "w",
        encoding="utf-8",
    ) as out:
        out.write(output_content)

    logger.info("Exported to: %s", final_destination_path)


if __name__ == "__main__":
    # initially the project were using 'print', but we moved to logging for better control.
    # To match with the initial behavior we set logging to debug level
    # and target stdout with simple message formater
    formatter = logging.Formatter("%(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # remove the existing handlers
    logger.handlers = []
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG)
    # this setting will make the 'python logseq-md-export.py' behave the same way as if
    # it were doing print; to not break compatibility with initial usage patterns.
    # Tho it can now be integrated in larger projects with more control over its logging behavior.

    parser = argparse.ArgumentParser(
        description="Export Logseq markdown file to a folder, adjusting formatting and importing assets."
    )
    parser.add_argument(
        "logseq_file",
        type=str,
        help="Path to the Logseq markdown file to export.",
    )
    parser.add_argument("output_path", type=str, help="Path to the output directory.")
    parser.add_argument(
        "--no-br",
        action="store_true",
        help="Do not insert <br> tags for empty lines.",
    )
    args: argparse.Namespace = parser.parse_args()
    export_file_to_folder(
        args.logseq_file,
        args.output_path,
        no_br=args.no_br,
    )
