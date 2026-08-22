#!/usr/bin/env python3
"""Build the editable and signed Download to NAS Apple Shortcut artifacts."""

import argparse
import plistlib
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).with_name("Download-to-NAS.plist")
SIGNED_PATH = Path(__file__).with_name("Download-to-NAS.shortcut")
DOCS_PATH = ROOT / "docs/mobile/assets/Download-to-NAS.shortcut"
OBJECT_REPLACEMENT = "\ufffc"
NAMESPACE = uuid.UUID("db6a665d-4ec8-49f8-88d8-9e245b20e43e")


def stable_uuid(name):
    return str(uuid.uuid5(NAMESPACE, name)).upper()


def output(name, output_name="Text"):
    return {
        "Type": "ActionOutput",
        "OutputUUID": stable_uuid(name),
        "OutputName": output_name,
    }


def variable(name):
    return {"Type": "Variable", "VariableName": name}


def extension_input():
    return {"Type": "ExtensionInput"}


def attachment(value):
    return {
        "Value": value,
        "WFSerializationType": "WFTextTokenAttachment",
    }


def text_token(*parts):
    text = ""
    attachments = {}
    for part in parts:
        if isinstance(part, str):
            text += part
            continue
        offset = len(text)
        text += OBJECT_REPLACEMENT
        attachments[f"{{{offset}, 1}}"] = part
    return {
        "Value": {
            "attachmentsByRange": attachments,
            "string": text,
        },
        "WFSerializationType": "WFTextTokenString",
    }


def dictionary_field(key, value):
    if isinstance(value, str):
        value = text_token(value)
    return {
        "WFItemType": 0,
        "WFKey": text_token(key),
        "WFValue": value,
    }


def action(identifier, **parameters):
    return {
        "WFWorkflowActionIdentifier": identifier,
        "WFWorkflowActionParameters": parameters,
    }


def text_action(name, value):
    return action(
        "is.workflow.actions.gettext",
        UUID=stable_uuid(name),
        WFTextActionText=value,
    )


def set_variable(name, value):
    return action(
        "is.workflow.actions.setvariable",
        WFInput=attachment(value),
        WFVariableName=name,
    )


def get_variable(name):
    return action(
        "is.workflow.actions.getvariable",
        WFVariable=attachment(variable(name)),
    )


def dictionary_value(name, key):
    return action(
        "is.workflow.actions.getvalueforkey",
        UUID=stable_uuid(name),
        WFDictionaryKey=key,
        WFGetDictionaryValueType="Value",
    )


def conditional_start(group, value, condition=100, expected=None):
    parameters = {
        "GroupingIdentifier": stable_uuid(group),
        "WFCondition": condition,
        "WFControlFlowMode": 0,
        "WFInput": {
            "Type": "Variable",
            "Variable": attachment(value),
        },
    }
    if expected is not None:
        parameters["WFConditionalActionString"] = expected
    return action("is.workflow.actions.conditional", **parameters)


def conditional_marker(group, mode, name=None):
    parameters = {
        "GroupingIdentifier": stable_uuid(group),
        "WFControlFlowMode": mode,
    }
    if name:
        parameters["UUID"] = stable_uuid(name)
    return action("is.workflow.actions.conditional", **parameters)


def menu_start(group, items, prompt):
    return action(
        "is.workflow.actions.choosefrommenu",
        GroupingIdentifier=stable_uuid(group),
        WFControlFlowMode=0,
        WFMenuItems=items,
        WFMenuPrompt=prompt,
    )


def menu_marker(group, mode, title=None, name=None):
    parameters = {
        "GroupingIdentifier": stable_uuid(group),
        "WFControlFlowMode": mode,
    }
    if title:
        parameters["WFMenuItemTitle"] = title
    if name:
        parameters["UUID"] = stable_uuid(name)
    return action("is.workflow.actions.choosefrommenu", **parameters)


def json_request(name, endpoint, fields):
    return action(
        "is.workflow.actions.downloadurl",
        UUID=stable_uuid(name),
        WFHTTPMethod="POST",
        WFJSONValues={
            "Value": {
                "WFDictionaryFieldValueItems": [
                    dictionary_field(key, value) for key, value in fields
                ],
            },
            "WFSerializationType": "WFDictionaryFieldValue",
        },
        WFURL=endpoint,
    )


def context_request(name):
    return json_request(
        name,
        text_token(output("server-base"), "/youtube-dl/share/context"),
        [
            ("text", text_token(variable("Shared Text"))),
            ("profile", text_token(variable("Profile"))),
            ("id", text_token(output("account-id"))),
            ("pw", text_token(output("account-password"))),
            ("client", "ios-shortcut"),
            ("client_version", "2.1"),
            ("soft_errors", "true"),
        ],
    )


def profile_menu_actions():
    group = "profile-menu"
    values = [
        ("Best", "best"),
        ("Compatible MP4", "compatible-mp4"),
        ("1080p", "1080p"),
        ("720p", "720p"),
        ("MP3", "audio-mp3"),
        ("M4A", "audio-m4a"),
    ]
    actions = [menu_start(group, [label for label, _ in values], "Download profile")]
    for index, (label, value) in enumerate(values):
        name = f"profile-choice-{index}"
        actions.extend([
            menu_marker(group, 1, title=label),
            text_action(name, value),
            set_variable("Profile", output(name)),
        ])
    actions.append(menu_marker(group, 2, name="profile-menu-end"))
    return actions


def playlist_menu_actions():
    group = "playlist-menu"
    return [
        menu_start(group, ["First 10 items", "All items"], "This link is a playlist or channel. Choose its scope."),
        menu_marker(group, 1, title="First 10 items"),
        text_action("playlist-first10", "first10"),
        set_variable("Playlist Mode", output("playlist-first10")),
        menu_marker(group, 1, title="All items"),
        text_action("playlist-all", "all"),
        set_variable("Playlist Mode", output("playlist-all")),
        menu_marker(group, 2, name="playlist-menu-end"),
    ]


def timestamp_menu_actions():
    group = "timestamp-menu"
    return [
        menu_start(
            group,
            ["Full video", "From shared timestamp"],
            text_token("Shared link starts at ", output("context-timestamp-label", "Dictionary Value"), "."),
        ),
        menu_marker(group, 1, title="Full video"),
        text_action("section-full-choice", "full"),
        set_variable("Section Mode", output("section-full-choice")),
        menu_marker(group, 1, title="From shared timestamp"),
        text_action("section-timestamp-choice", "from_timestamp"),
        set_variable("Section Mode", output("section-timestamp-choice")),
        menu_marker(group, 2, name="timestamp-menu-end"),
    ]


def build_workflow():
    actions = [
        action(
            "is.workflow.actions.comment",
            WFCommentActionText=(
                "Smart Share v2 sends a shared media URL directly to youtube-dl-nas. "
                "Server address and credentials are entered once during import."
            ),
        ),
        text_action("server-base", "http://NAS_ADDRESS:8080"),
        text_action("account-id", "YOUR_ID"),
        text_action("account-password", "YOUR_PASSWORD"),
        text_action("default-profile", "best"),
        conditional_start("input-present", extension_input()),
        set_variable("Shared Text", extension_input()),
        conditional_marker("input-present", 1),
        action(
            "is.workflow.actions.ask",
            UUID=stable_uuid("manual-url"),
            WFAskActionDefaultAnswerURL="",
            WFAskActionPrompt="Paste a YouTube or media URL",
            WFInputType="URL",
        ),
        set_variable("Shared Text", output("manual-url", "Provided Input")),
        conditional_marker("input-present", 2, name="input-present-end"),
        conditional_start("profile-ask", output("default-profile"), condition=4, expected="ask"),
    ]
    actions.extend(profile_menu_actions())
    actions.extend([
        conditional_marker("profile-ask", 1),
        set_variable("Profile", output("default-profile")),
        conditional_marker("profile-ask", 2, name="profile-ask-end"),
        context_request("context-request"),
        set_variable("Share Context", output("context-request", "Contents of URL")),
        get_variable("Share Context"),
        dictionary_value("context-url", "url"),
        conditional_start("context-url-present", output("context-url", "Dictionary Value")),
        set_variable("Media URL", output("context-url", "Dictionary Value")),
        conditional_marker("context-url-present", 1),
        action(
            "is.workflow.actions.ask",
            UUID=stable_uuid("missing-shared-url"),
            WFAskActionDefaultAnswerURL="",
            WFAskActionPrompt="No URL was found in the shared text. Paste the media URL.",
            WFInputType="URL",
        ),
        set_variable("Shared Text", output("missing-shared-url", "Provided Input")),
        context_request("context-request-retry"),
        set_variable("Share Context", output("context-request-retry", "Contents of URL")),
        get_variable("Share Context"),
        dictionary_value("context-url-retry", "url"),
        set_variable("Media URL", output("context-url-retry", "Dictionary Value")),
        conditional_marker("context-url-present", 2, name="context-url-present-end"),
        get_variable("Share Context"),
        dictionary_value("context-playlist-kind", "playlist_kind"),
        conditional_start("playlist-present", output("context-playlist-kind", "Dictionary Value")),
    ])
    actions.extend(playlist_menu_actions())
    actions.extend([
        conditional_marker("playlist-present", 1),
        text_action("playlist-single", "single"),
        set_variable("Playlist Mode", output("playlist-single")),
        conditional_marker("playlist-present", 2, name="playlist-present-end"),
        get_variable("Share Context"),
        dictionary_value("context-timestamp-label", "timestamp_label"),
        conditional_start("timestamp-present", output("context-timestamp-label", "Dictionary Value")),
    ])
    actions.extend(timestamp_menu_actions())
    actions.extend([
        conditional_marker("timestamp-present", 1),
        text_action("section-full-default", "full"),
        set_variable("Section Mode", output("section-full-default")),
        conditional_marker("timestamp-present", 2, name="timestamp-present-end"),
        json_request(
            "queue-request",
            text_token(output("server-base"), "/youtube-dl/rest"),
            [
                ("url", text_token(variable("Media URL"))),
                ("resolution", text_token(variable("Profile"))),
                ("playlist_mode", text_token(variable("Playlist Mode"))),
                ("section_mode", text_token(variable("Section Mode"))),
                ("id", text_token(output("account-id"))),
                ("pw", text_token(output("account-password"))),
                ("client", "ios-shortcut"),
                ("client_version", "2.1"),
            ],
        ),
        set_variable("Queue Response", output("queue-request", "Contents of URL")),
        get_variable("Queue Response"),
        dictionary_value("queue-message", "msg"),
        action(
            "is.workflow.actions.showresult",
            Text=text_token(output("queue-message", "Dictionary Value")),
        ),
    ])

    import_questions = [
        {
            "ActionIndex": 1,
            "Category": "Parameter",
            "DefaultValue": "http://NAS_ADDRESS:8080",
            "ParameterKey": "WFTextActionText",
            "Text": "NAS base URL, without a trailing slash (for example http://192.168.0.20:8080)",
        },
        {
            "ActionIndex": 2,
            "Category": "Parameter",
            "DefaultValue": "YOUR_ID",
            "ParameterKey": "WFTextActionText",
            "Text": "youtube-dl-nas dashboard ID",
        },
        {
            "ActionIndex": 3,
            "Category": "Parameter",
            "DefaultValue": "YOUR_PASSWORD",
            "ParameterKey": "WFTextActionText",
            "Text": "youtube-dl-nas dashboard password",
        },
        {
            "ActionIndex": 4,
            "Category": "Parameter",
            "DefaultValue": "best",
            "ParameterKey": "WFTextActionText",
            "Text": "Default profile: best, compatible-mp4, 1080p, 720p, audio-mp3, audio-m4a, or ask",
        },
    ]

    return {
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "4610",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 61440,
            "WFWorkflowIconStartColor": -1263359489,
        },
        "WFWorkflowImportQuestions": import_questions,
        "WFWorkflowInputContentItemClasses": [
            "WFStringContentItem",
            "WFRichTextContentItem",
            "WFSafariWebPageContentItem",
            "WFURLContentItem",
            "WFArticleContentItem",
        ],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": ["ActionExtension", "WFWorkflowTypeShowInSearch"],
    }


def source_bytes():
    return plistlib.dumps(build_workflow(), fmt=plistlib.FMT_XML, sort_keys=False)


def write_source(check=False):
    rendered = source_bytes()
    if check:
        if not SOURCE_PATH.exists() or SOURCE_PATH.read_bytes() != rendered:
            raise SystemExit("Download-to-NAS.plist is out of date; run build_shortcut.py")
        return
    SOURCE_PATH.write_bytes(rendered)


def sign_shortcut():
    with tempfile.NamedTemporaryFile(suffix=".wflow") as unsigned:
        unsigned.write(plistlib.dumps(build_workflow(), fmt=plistlib.FMT_BINARY, sort_keys=False))
        unsigned.flush()
        subprocess.run(
            [
                "shortcuts",
                "sign",
                "--mode",
                "anyone",
                "--input",
                unsigned.name,
                "--output",
                str(SIGNED_PATH),
            ],
            check=True,
        )
    DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SIGNED_PATH, DOCS_PATH)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify the committed plist")
    parser.add_argument("--sign", action="store_true", help="sign and copy installable artifacts on macOS")
    args = parser.parse_args()
    write_source(check=args.check)
    if args.sign:
        sign_shortcut()


if __name__ == "__main__":
    main()
