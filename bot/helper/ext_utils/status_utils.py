from html import escape
from math import e
from psutil import (
    virtual_memory,
    cpu_percent,
    disk_usage
)
from time import time
from asyncio import iscoroutinefunction

from bot import (
    DOWNLOAD_DIR,
    task_dict,
    task_dict_lock,
    bot_start_time,
    config_dict,
    status_dict,
)
from .bot_utils import sync_to_async
from ..telegram_helper.button_build import ButtonMaker
from ..telegram_helper.bot_commands import BotCommands

SIZE_UNITS = [
    "B",
    "KB",
    "MB",
    "GB",
    "TB",
    "PB"
]

# --- CUSTOM EMOJIS ---
EM_1 = '<tg-emoji emoji-id="5877219383691972108">➕</tg-emoji>'
EM_2 = '<tg-emoji emoji-id="5195111279244619776">🍀</tg-emoji>'
EM_3 = '<tg-emoji emoji-id="5287533898803211359">📫</tg-emoji>'
EM_4 = '<tg-emoji emoji-id="5411590687663608498">⚡</tg-emoji>'
EM_5 = '<tg-emoji emoji-id="5422407403884798028">🍀</tg-emoji>'
EM_6 = '<tg-emoji emoji-id="5424867354993513047">🌷</tg-emoji>'
EM_7 = '<tg-emoji emoji-id="5443127283898405358">⬇️</tg-emoji>'
EM_8 = '<tg-emoji emoji-id="5445355530111437729">⬆️</tg-emoji>'
EM_9 = '<tg-emoji emoji-id="5765005318610228026">❌</tg-emoji>'
EM_10 = '<tg-emoji emoji-id="5285439518130857782">❤️</tg-emoji>'
EM_11 = '<tg-emoji emoji-id="5190642636356072894">☔️</tg-emoji>'
EM_12 = '<tg-emoji emoji-id="5256218768262056531">🟪</tg-emoji>'
EM_13 = '<tg-emoji emoji-id="5285535716808342592">☠️</tg-emoji>'
# ---------------------


class MirrorStatus:
    STATUS_UPLOADING = "Upload 📤"
    STATUS_DOWNLOADING = "Download 📥"
    STATUS_CLONING = "Clone 🔃"
    STATUS_QUEUEDL = "QueueDL ⏳"
    STATUS_QUEUEUP = "QueueUL ⏳"
    STATUS_PAUSED = "Paused ⛔️"
    STATUS_ARCHIVING = "Archive 🛠"
    STATUS_EXTRACTING = "Extract 📂"
    STATUS_SPLITTING = "Split ✂️"
    STATUS_CHECKING = "CheckUp ⏱"
    STATUS_SEEDING = "Seed 🌧"
    STATUS_SAMVID = "SampleVid 🎬"
    STATUS_CONVERTING = "Convert ♻️"
    STATUS_METADATA = "Metadata 📝"


STATUSES = {
    "ALL": "All",
    "DL": MirrorStatus.STATUS_DOWNLOADING,
    "UP": MirrorStatus.STATUS_UPLOADING,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVING,
    "EX": MirrorStatus.STATUS_EXTRACTING,
    "SD": MirrorStatus.STATUS_SEEDING,
    "CM": MirrorStatus.STATUS_CONVERTING,
    "CL": MirrorStatus.STATUS_CLONING,
    "SP": MirrorStatus.STATUS_SPLITTING,
    "CK": MirrorStatus.STATUS_CHECKING,
    "SV": MirrorStatus.STATUS_SAMVID,
    "PA": MirrorStatus.STATUS_PAUSED,
    "MD": MirrorStatus.STATUS_METADATA
}


async def get_task_by_gid(gid: str):
    async with task_dict_lock:
        for tk in task_dict.values():
            if hasattr(
                tk,
                "seeding"
            ):
                await sync_to_async(tk.update)
            if tk.gid() == gid:
                return tk
        return None


def get_specific_tasks(status, user_id):
    if status == "All":
        if user_id:
            return [
                tk
                for tk
                in task_dict.values()
                if tk.listener.user_id == user_id
            ]
        else:
            return list(task_dict.values())
    elif user_id:
        return [
            tk
            for tk in task_dict.values()
            if tk.listener.user_id == user_id
            and (
                (st := tk.status())
                and st == status
                or status == MirrorStatus.STATUS_DOWNLOADING
                and st not in STATUSES.values()
            )
        ]
    else:
        return [
            tk
            for tk in task_dict.values()
            if (st := tk.status())
            and st == status
            or status == MirrorStatus.STATUS_DOWNLOADING
            and st not in STATUSES.values()
        ]


async def get_all_tasks(req_status: str, user_id):
    async with task_dict_lock:
        return await sync_to_async(
            get_specific_tasks,
            req_status,
            user_id
        )


def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds):
    periods = [
        ("d", 86400),
        ("h", 3600),
        ("m", 60),
        ("s", 1)
    ]
    result = ""
    for (
        period_name,
        period_seconds
    ) in periods:
        if seconds >= period_seconds:
            (
                period_value,
                seconds
            ) = divmod(
                seconds,
                period_seconds
            )
            result += f"{int(period_value)}{period_name}"
    return result


def time_to_seconds(time_duration):
    (
        hours,
        minutes,
        seconds
    ) = map(int, time_duration.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def speed_string_to_bytes(size_text: str):
    size = 0
    size_text = size_text.lower()
    if "k" in size_text:
        size += float(size_text.split("k")[0]) * 1024
    elif "m" in size_text:
        size += float(size_text.split("m")[0]) * 1048576
    elif "g" in size_text:
        size += float(size_text.split("g")[0]) * 1073741824
    elif "t" in size_text:
        size += float(size_text.split("t")[0]) * 1099511627776
    elif "b" in size_text:
        size += float(size_text.split("b")[0])
    return size


def get_progress_bar_string(pct):
    if isinstance(pct, str):
        pct = float(pct.strip("%"))
    p = min(
        max(pct, 0),
        100
    )
    cFull = int(p // 8)
    PRG_FULL = '<tg-emoji emoji-id="5422682311856501431">🌷</tg-emoji>'
    PRG_EMPTY = '<tg-emoji emoji-id="5971816626796892111">🔹</tg-emoji>'
    
    p_str = PRG_FULL * cFull
    p_str += PRG_EMPTY * (12 - cFull)
    return f"[{p_str}]"


async def get_readable_message(
        sid,
        is_user,
        page_no=1,
        status="All",
        page_step=1
    ):
    msg = ""
    button = None

    tasks = await sync_to_async(
        get_specific_tasks,
        status,
        sid
        if is_user
        else None
    )

    STATUS_LIMIT = config_dict["STATUS_LIMIT"]
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict[sid]["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict[sid]["page_no"] = page_no
    start_position = (page_no - 1) * STATUS_LIMIT

    for index, task in enumerate(
        tasks[start_position : STATUS_LIMIT + start_position],
        start=1
    ):
        tstatus = (
            await sync_to_async(task.status)
            if status == "All"
            else status
        )
        elapse = time() - task.listener.time
        elapsed = (
            "-"
            if elapse < 1
            else get_readable_time(elapse)
        )
        user_tag = task.listener.tag.replace("@", "").replace("_", " ")
        cancel_task = (
            f"<code>/{BotCommands.CancelTaskCommand[1]} {task.gid()}</code>"
            if not task.listener.get_chat.has_protected_content
            else f"<b>/{BotCommands.CancelTaskCommand[1]}_{task.gid()}</b>"
        )

        if (
            config_dict["DELETE_LINKS"]
            and int(config_dict["AUTO_DELETE_MESSAGE_DURATION"]) > 0
        ):
            msg += (
                f"<b><i>\n#Zee{index + start_position}: "
                f"{escape(f'{task.name()}')}\n</i></b>"
                if elapse <= config_dict["AUTO_DELETE_MESSAGE_DURATION"]
                else f"\n<b>#Zee{index + start_position}...(Processing)</b>"
            )
        else:
            msg += (
                f"<b><i>\n#Zee{index + start_position}: "
                f"{escape(f'{task.name()}')}\n</i></b>"
            )
        if tstatus not in [
            MirrorStatus.STATUS_SEEDING,
            MirrorStatus.STATUS_QUEUEDL,
            MirrorStatus.STATUS_QUEUEUP,
            MirrorStatus.STATUS_METADATA
        ]:
            progress = (
                await task.progress()
                if iscoroutinefunction(task.progress)
                else task.progress()
            )
            msg += (
                f"\n{EM_1} {get_progress_bar_string(progress)} <b><i>{progress}</i></b>"
                f"\n{EM_3} <b>Status</b> → <b>{tstatus}</b>"
                f"\n{EM_2} <b>Done</b> → <i>{task.processed_bytes()} of {task.size()}</i>"
                f"\n{EM_4} <b>Speed</b> → <i>{task.speed()}</i>"
                f"\n{EM_5} <b>ETA</b> → <i>{task.eta()}</i>"
                f"\n{EM_5} <b>Past</b> → <i>{elapsed}</i>"
                f"\n👤 <b>User</b> → <b>{user_tag}</b>"
                f"\n🆔 <b>UserID</b> → ||{task.listener.user_id}||"
                f"\n{EM_7} <b>Upload</b> → <i>{task.listener.mode}</i>"
                f"\n{EM_13} <b>Engine</b> → <b><i>{task.engine}</i></b>"
            )
            if hasattr(
                task,
                "playList"
            ):
                try:
                    if playlist := task.playList():
                        msg += f"\n<code>YtList :</code> {playlist}"
                except:
                    pass
            if hasattr(
                task,
                "seeders_num"
            ):
                try:
                    msg += f"\n{EM_2} <b>S/L</b> → <i>{task.seeders_num()}/{task.leechers_num()}</i>"
                except:
                    pass
        elif tstatus == MirrorStatus.STATUS_SEEDING:
            msg += (
                f"\n{EM_6} <b>Size</b> → <i>{task.size()}</i> | <b>Uploaded</b> → <i>{task.uploaded_bytes()}</i>"
                f"\n{EM_3} <b>Status</b> → <b>{tstatus}</b>"
                f"\n{EM_4} <b>Speed</b> → <i>{task.seed_speed()}</i>"
                f"\n{EM_1} <b>Ratio</b> → <i>{task.ratio()}</i>"
                f"\n{EM_5} <b>Time</b> → <i>{task.seeding_time()}</i> | <b>Elapsed</b> → <i>{elapsed}</i>"
            )
        else:
            msg += (
                f"\n{EM_3} <b>Status</b> → <b>{tstatus}</b>"
                f"\n{EM_6} <b>Size</b> → <i>{task.size()}</i>"
                f"\n{EM_7} <b>Upload</b> → <i>{task.listener.mode}</i>"
                f"\n{EM_5} <b>Past</b> → <i>{elapsed}</i>"
                f"\n👤 <b>User</b> → <i>{user_tag}</i>"
                f"\n🆔 <b>UserID</b> → ||{task.listener.user_id}||"
                f"\n{EM_13} <b>Engine</b> → <i>{task.engine}</i>"
            )
        msg += f"\n{EM_9} {cancel_task}\n\n"

    if len(msg) == 0:
        if status == "All":
            return (
                None,
                None
            )
        else:
            msg = f"No Active {status} Tasks!\n\n"
    buttons = ButtonMaker()
    if is_user:
        buttons.data_button(
            "ʀᴇғʀᴇsʜ",
            f"status {sid} ref",
            position="header"
        )
    if not is_user:
        buttons.data_button(
            "ᴛᴀsᴋs\nɪɴғᴏ",
            f"status {sid} ov",
            position="footer"
        )
        buttons.data_button(
            "sʏsᴛᴇᴍ\nɪɴғᴏ",
            f"status {sid} stats",
            position="footer"
        )
    if len(tasks) > STATUS_LIMIT:
        msg += f"<b>Tasks:</b> {tasks_no} | <b>Step:</b> {page_step}\n"
        buttons.data_button(
            "⫷",
            f"status {sid} pre",
            position="header"
        )
        buttons.data_button(
            f"ᴘᴀɢᴇs\n{page_no}/{pages}",
            f"status {sid} ref",
            position="header"
        )
        buttons.data_button(
            "⫸",
            f"status {sid} nex",
            position="header"
        )
        if tasks_no > 30:
            for i in [
                1,
                2,
                4,
                6,
                8,
                10,
                15
            ]:
                buttons.data_button(
                    i,
                    f"status {sid} ps {i}"
                )
    if (
        status != "All" or
        tasks_no > 20
    ):
        for (
            label,
            status_value
        ) in list(STATUSES.items())[:9]:
            if status_value != status:
                buttons.data_button(
                    label,
                    f"status {sid} st {status_value}"
                )
    button = buttons.build_menu(8)
    msg += (
        f"\n{EM_12} <b><u>Bot Stats</u></b>\n"
        f"{EM_10} <b>CPU</b> → {cpu_percent()}% | "
        f"<b>FREE</b> → {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)} [{round(100 - disk_usage(DOWNLOAD_DIR).percent, 1)}%]\n"
        f"{EM_11} <b>RAM</b> → {virtual_memory().percent}% | "
        f"<b>UPTM</b> → {get_readable_time(time() - bot_start_time)}"
    )
    return (
        msg,
        button
    )
