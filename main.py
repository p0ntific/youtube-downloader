import flet as ft
import yt_dlp
import threading
import re
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class DownloadItem:
    id: str
    url: str
    status: str = "idle"
    progress: float = 0
    title: str = ""
    filename: str = ""
    error: Optional[str] = None
    cancel_flag: bool = False


class YouTubeDownloader:
    YOUTUBE_REGEX = re.compile(
        r'^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[a-zA-Z0-9_-]{11}'
    )

    def __init__(self, page: ft.Page):
        self.page = page
        self.items: dict[str, DownloadItem] = {}
        self.item_controls: dict[str, ft.Container] = {}
        self.download_path = Path.home() / "Downloads"

        self._setup_page()
        self._build_ui()

    def _setup_page(self):
        self.page.title = "YouTube Загрузчик"
        self.page.window.width = 700
        self.page.window.height = 650
        self.page.window.min_width = 550
        self.page.window.min_height = 500
        self.page.bgcolor = "#FAFAFA"
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = ft.Theme(
            color_scheme_seed="#FF0000",
            font_family="SF Pro Text, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        )

    def _validate_url(self, url: str) -> Optional[str]:
        if not url.strip():
            return None
        if not self.YOUTUBE_REGEX.match(url):
            return "Некорректная ссылка YouTube"
        return None

    def _generate_id(self) -> str:
        import random
        import string
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def _create_input_row(self, item_id: str) -> ft.Container:
        item = self.items[item_id]

        url_field = ft.TextField(
            value=item.url,
            hint_text="Вставьте ссылку на видео...",
            border_radius=14,
            bgcolor="#FFFFFF",
            border_color="#E5E7EB",
            focused_border_color="#EF4444",
            cursor_color="#EF4444",
            text_size=14,
            content_padding=ft.Padding(16, 14, 50, 14),
            expand=True,
            on_change=lambda e: self._on_url_change(item_id, e.control.value),
        )

        title_text = ft.Text(
            "",
            size=13,
            color="#374151",
            weight=ft.FontWeight.W_500,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            visible=False,
        )

        file_text = ft.Text(
            "",
            size=11,
            color="#6B7280",
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            visible=False,
        )

        progress_bar = ft.ProgressBar(
            value=0,
            bgcolor="#E5E7EB",
            color="#EF4444",
            bar_height=6,
            border_radius=3,
            visible=False,
        )

        progress_text = ft.Text(
            "",
            size=13,
            color="#6B7280",
            weight=ft.FontWeight.W_600,
        )

        cancel_btn = ft.TextButton(
            "Отменить",
            style=ft.ButtonStyle(
                color="#EF4444",
                padding=ft.Padding(8, 4, 8, 4),
                mouse_cursor=ft.MouseCursor.CLICK,
            ),
            on_click=lambda e: self._on_cancel(item_id),
        )

        progress_row = ft.Row(
            [
                progress_text,
                ft.Container(expand=True),
                cancel_btn,
            ],
            visible=False,
        )

        clear_btn = ft.IconButton(
            icon=ft.Icons.CLOSE_ROUNDED,
            icon_size=18,
            icon_color="#9CA3AF",
            tooltip="Очистить" if len(self.items) == 1 else "Удалить",
            on_click=lambda e: self._on_clear(item_id),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=6,
                mouse_cursor=ft.MouseCursor.CLICK,
            ),
        )

        status_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE,
            size=20,
            color="#10B981",
            visible=False,
        )

        error_text = ft.Text(
            "",
            size=12,
            color="#EF4444",
            visible=False,
        )

        input_row = ft.Stack(
            [
                url_field,
                ft.Container(
                    content=ft.Row([status_icon, clear_btn], spacing=4),
                    right=6,
                    top=0,
                    bottom=0,
                ),
            ],
        )

        container = ft.Container(
            content=ft.Column(
                [
                    input_row,
                    title_text,
                    progress_bar,
                    progress_row,
                    file_text,
                    error_text,
                ],
                spacing=8,
            ),
            padding=ft.Padding(20, 16, 20, 16),
            bgcolor="#FFFFFF",
            border_radius=20,
            border=ft.border.all(1, "#E5E7EB"),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=8,
                color="#0000000A",
                offset=ft.Offset(0, 2),
            ),
            data={
                "url_field": url_field,
                "title_text": title_text,
                "file_text": file_text,
                "progress_bar": progress_bar,
                "progress_row": progress_row,
                "progress_text": progress_text,
                "clear_btn": clear_btn,
                "status_icon": status_icon,
                "error_text": error_text,
            },
        )

        return container

    def _on_url_change(self, item_id: str, url: str):
        if item_id not in self.items:
            return

        self.items[item_id].url = url
        self.items[item_id].status = "idle"
        self.items[item_id].progress = 0
        self.items[item_id].error = None
        self.items[item_id].title = ""
        self.items[item_id].filename = ""

        container = self.item_controls[item_id]
        data = container.data

        error = self._validate_url(url)
        data["error_text"].value = error or ""
        data["error_text"].visible = bool(error)
        data["url_field"].border_color = "#EF4444" if error else "#E5E7EB"
        data["status_icon"].visible = False
        data["title_text"].visible = False
        data["file_text"].visible = False

        self._update_download_btn()
        self.page.update()

    def _on_clear(self, item_id: str):
        if len(self.items) == 1:
            self.items[item_id].url = ""
            self.items[item_id].status = "idle"
            self.items[item_id].progress = 0
            self.items[item_id].title = ""
            self.items[item_id].filename = ""
            self.items[item_id].error = None
            self.items[item_id].cancel_flag = False
            container = self.item_controls[item_id]
            container.data["url_field"].value = ""
            container.data["url_field"].disabled = False
            container.data["url_field"].bgcolor = "#FFFFFF"
            container.data["url_field"].border_color = "#E5E7EB"
            container.data["error_text"].visible = False
            container.data["status_icon"].visible = False
            container.data["title_text"].visible = False
            container.data["file_text"].visible = False
            container.data["progress_bar"].visible = False
            container.data["progress_row"].visible = False
            container.border = ft.border.all(1, "#E5E7EB")
        else:
            self.items[item_id].cancel_flag = True
            del self.items[item_id]
            self.inputs_column.controls.remove(self.item_controls[item_id])
            del self.item_controls[item_id]

        self._update_download_btn()
        self.page.update()

    def _on_cancel(self, item_id: str):
        if item_id in self.items:
            self.items[item_id].cancel_flag = True
            self.items[item_id].status = "cancelled"
            self._update_item_ui(item_id)

    def _on_add(self, e):
        item_id = self._generate_id()
        self.items[item_id] = DownloadItem(id=item_id, url="")
        container = self._create_input_row(item_id)
        self.item_controls[item_id] = container
        self.inputs_column.controls.insert(-1, container)
        self._update_download_btn()
        self.page.update()

    def _on_download(self, e):
        for item_id, item in self.items.items():
            if item.url.strip() and not self._validate_url(item.url) and item.status not in ["downloading", "completed"]:
                self._start_download(item_id)

    def _start_download(self, item_id: str):
        item = self.items[item_id]
        item.status = "downloading"
        item.progress = 0
        item.error = None
        item.cancel_flag = False
        item.title = "Получение информации..."
        self._update_item_ui(item_id)

        def progress_hook(d: dict[str, Any]):
            if item.cancel_flag:
                raise yt_dlp.utils.DownloadCancelled("Отменено пользователем")

            status = d.get('status')

            if status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)

                if total:
                    item.progress = (downloaded / total) * 100
                else:
                    item.progress = 0

                filename = d.get('filename', '')
                if filename and not item.title:
                    item.title = Path(filename).stem
                    item.filename = filename

                self.page.run_thread(lambda: self._update_item_ui(item_id))

            elif status == 'finished':
                item.progress = 100
                filename = d.get('filename', '')
                if filename:
                    item.filename = filename
                    item.title = Path(filename).stem
                self.page.run_thread(lambda: self._update_item_ui(item_id))

        def download():
            # Ensure download path exists
            self.download_path.mkdir(parents=True, exist_ok=True)
            output_template = str(self.download_path / "%(title)s.%(ext)s")

            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': output_template,
                'progress_hooks': [progress_hook],
                'quiet': True,
                'no_warnings': True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Get info first
                    info = ydl.extract_info(item.url, download=False)
                    if info:
                        item.title = info.get('title', 'Загрузка...')
                        self.page.run_thread(lambda: self._update_item_ui(item_id))

                    # Check if already downloaded
                    expected_file = Path(output_template % {'title': info.get('title', ''), 'ext': info.get('ext', 'mp4')})
                    if expected_file.exists():
                        item.filename = str(expected_file)
                        item.status = "exists"
                        item.progress = 100
                        self.page.run_thread(lambda: self._update_item_ui(item_id))
                        self.page.run_thread(lambda: self._show_exists_snackbar(item.title))
                        return

                    if item.cancel_flag:
                        item.status = "cancelled"
                        return

                    # Download
                    ydl.download([item.url])

                if item.status not in ["cancelled", "exists"]:
                    item.status = "completed"
                    item.progress = 100

            except yt_dlp.utils.DownloadCancelled:
                item.status = "cancelled"
            except Exception as ex:
                item.status = "error"
                error_msg = str(ex)
                if "Sign in" in error_msg or "login" in error_msg.lower():
                    item.error = "Требуется авторизация в Chrome"
                elif "unavailable" in error_msg.lower():
                    item.error = "Видео недоступно"
                elif "private" in error_msg.lower():
                    item.error = "Приватное видео"
                elif "cookie" in error_msg.lower():
                    item.error = "Ошибка cookies Chrome"
                elif "No such file" in error_msg or "path" in error_msg.lower():
                    item.error = f"Ошибка пути: {error_msg[:50]}"
                elif "blocked" in error_msg.lower() or "geo" in error_msg.lower():
                    item.error = "Видео заблокировано в регионе"
                else:
                    # Show actual error for debugging
                    short_error = error_msg[:100] if len(error_msg) > 100 else error_msg
                    item.error = short_error
            finally:
                self.page.run_thread(lambda: self._update_item_ui(item_id))

        threading.Thread(target=download, daemon=True).start()

    def _show_exists_snackbar(self, title: str):
        snack = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINE, color="#FFFFFF", size=20),
                    ft.Text(
                        f"Файл уже скачан: {title[:40]}{'...' if len(title) > 40 else ''}",
                        color="#FFFFFF",
                        size=14,
                    ),
                ],
                spacing=12,
            ),
            bgcolor="#3B82F6",
            duration=4000,
            open=True,
        )
        self.page.overlay.append(snack)
        self.page.update()

    def _update_item_ui(self, item_id: str):
        if item_id not in self.items or item_id not in self.item_controls:
            return

        item = self.items[item_id]
        container = self.item_controls[item_id]
        data = container.data

        is_downloading = item.status == "downloading"
        is_completed = item.status == "completed"
        is_exists = item.status == "exists"
        is_error = item.status == "error"
        is_done = is_completed or is_exists

        # URL field state
        data["url_field"].disabled = is_downloading or is_done
        data["url_field"].bgcolor = "#F9FAFB" if (is_downloading or is_done) else "#FFFFFF"

        # Title
        data["title_text"].value = item.title
        data["title_text"].visible = bool(item.title) and (is_downloading or is_done)
        data["title_text"].color = "#374151"

        if is_completed:
            data["title_text"].color = "#10B981"
            data["title_text"].value = f"✓ {item.title}"
        elif is_exists:
            data["title_text"].color = "#3B82F6"
            data["title_text"].value = f"📦 Уже скачан: {item.title}"

        # File path
        if is_done and item.filename:
            data["file_text"].value = f"📁 {item.filename}"
            data["file_text"].visible = True
        else:
            data["file_text"].visible = False

        # Border color
        if is_completed:
            container.border = ft.border.all(2, "#10B981")
            data["status_icon"].visible = True
            data["status_icon"].name = ft.Icons.CHECK_CIRCLE
            data["status_icon"].color = "#10B981"
        elif is_exists:
            container.border = ft.border.all(2, "#3B82F6")
            data["status_icon"].visible = True
            data["status_icon"].name = ft.Icons.INVENTORY_2
            data["status_icon"].color = "#3B82F6"
        elif is_error:
            container.border = ft.border.all(2, "#EF4444")
            data["status_icon"].visible = True
            data["status_icon"].name = ft.Icons.ERROR
            data["status_icon"].color = "#EF4444"
        elif is_downloading:
            container.border = ft.border.all(2, "#EF4444")
            data["status_icon"].visible = False
        else:
            container.border = ft.border.all(1, "#E5E7EB")
            data["status_icon"].visible = False

        # Progress
        data["progress_bar"].visible = is_downloading
        data["progress_bar"].value = item.progress / 100

        data["progress_row"].visible = is_downloading
        data["progress_text"].value = f"{int(item.progress)}%"

        # Buttons
        data["clear_btn"].visible = not is_downloading

        # Error
        data["error_text"].visible = bool(item.error)
        data["error_text"].value = item.error or ""

        self._update_download_btn()
        self.page.update()

    def _update_download_btn(self):
        has_valid = any(
            item.url.strip() and not self._validate_url(item.url) and item.status not in ["downloading", "completed", "exists"]
            for item in self.items.values()
        )
        is_downloading = any(item.status == "downloading" for item in self.items.values())

        self.download_btn.disabled = not has_valid
        if is_downloading:
            self.download_btn.text = "Загрузка..."
            self.download_btn.icon = ft.Icons.HOURGLASS_TOP
        else:
            self.download_btn.text = "Скачать"
            self.download_btn.icon = ft.Icons.DOWNLOAD_ROUNDED

    def _get_download_path_display(self) -> str:
        """Returns display path for current OS"""
        if os.name == "nt":
            # Windows: show full path
            return str(self.download_path)
        else:
            # macOS/Linux: show with ~
            home = Path.home()
            try:
                rel = self.download_path.relative_to(home)
                return f"~/{rel}"
            except ValueError:
                return str(self.download_path)

    def _open_folder(self, e):
        import subprocess
        if os.name == "nt":
            os.startfile(self.download_path)
        elif os.name == "posix":
            subprocess.run(["open", self.download_path])

    def _build_ui(self):
        # Download path display
        path_row = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER_ROUNDED, size=18, color="#EF4444"),
                    ft.Text(
                        self._get_download_path_display(),
                        size=13,
                        color="#6B7280",
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
                        icon_size=18,
                        icon_color="#9CA3AF",
                        tooltip="Открыть папку",
                        on_click=self._open_folder,
                        style=ft.ButtonStyle(
                            padding=4,
                            mouse_cursor=ft.MouseCursor.CLICK,
                        ),
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor="#FFFFFF",
            padding=ft.Padding(16, 12, 8, 12),
            border_radius=12,
            border=ft.border.all(1, "#E5E7EB"),
        )

        # Version info
        version_text = ft.Text(
            f"yt-dlp {yt_dlp.version.__version__}",
            size=12,
            color="#9CA3AF",
        )

        # Initial input
        initial_id = self._generate_id()
        self.items[initial_id] = DownloadItem(id=initial_id, url="")
        initial_container = self._create_input_row(initial_id)
        self.item_controls[initial_id] = initial_container

        # Add button
        add_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD_ROUNDED, size=22, color="#9CA3AF"),
                    ft.Text("Добавить ещё ссылку", size=14, color="#9CA3AF", weight=ft.FontWeight.W_500),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.Padding(20, 16, 20, 16),
            bgcolor="#FFFFFF",
            border_radius=20,
            border=ft.border.all(2, "#E5E7EB"),
            ink=True,
            ink_color="#EF444420",
            on_click=self._on_add,
        )

        self.inputs_column = ft.Column(
            [initial_container, add_btn],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # Download button
        self.download_btn = ft.ElevatedButton(
            "Скачать",
            icon=ft.Icons.DOWNLOAD_ROUNDED,
            bgcolor="#EF4444",
            color="#FFFFFF",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=16),
                padding=ft.Padding(32, 18, 32, 18),
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_600),
                mouse_cursor=ft.MouseCursor.CLICK,
            ),
            disabled=True,
            on_click=self._on_download,
        )

        # Birthday banner
        birthday_banner = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "подарок для мамы  ·  с днём рождения",
                        size=12,
                        weight=ft.FontWeight.W_500,
                        color="#ffffff",
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            gradient=ft.LinearGradient(
                begin=ft.Alignment(-1, 0),
                end=ft.Alignment(1, 0),
                colors=["#7d5a6b", "#9b7a8a", "#c4a57b", "#9b7a8a", "#7d5a6b"],
            ),
            padding=ft.Padding(0, 9, 0, 9),
        )

        # Main layout
        content = ft.Container(
            content=ft.Column(
                [
                    birthday_banner,
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.PLAY_CIRCLE_FILLED, size=32, color="#EF4444"),
                                        ft.Text(
                                            "YouTube Загрузчик",
                                            size=22,
                                            weight=ft.FontWeight.W_700,
                                            color="#111827",
                                        ),
                                        ft.Container(expand=True),
                                        version_text,
                                    ],
                                    spacing=12,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Container(height=8),
                                path_row,
                                ft.Container(height=16),
                                self.inputs_column,
                                ft.Container(height=8),
                                ft.Row(
                                    [self.download_btn],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                            ],
                        ),
                        padding=ft.Padding(24, 20, 24, 24),
                        expand=True,
                    ),
                ],
                spacing=0,
            ),
            expand=True,
        )

        self.page.add(content)


def main(page: ft.Page):
    YouTubeDownloader(page)


if __name__ == "__main__":
    ft.app(main)
