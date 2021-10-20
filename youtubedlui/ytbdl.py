import sys
import os
import re
import shutil

import yt_dlp
from PySide2.QtCore import Qt, QThread, Signal, QSettings
from PySide2.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QPlainTextEdit, QLabel, QPushButton, QLineEdit,
                               QFileDialog, QComboBox, QCheckBox, QMessageBox,
                               QProgressDialog)


class YtbLogger(object):

    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


class YtbInfo(QThread):

    OPTS = {
        "logger": YtbLogger(),
        "extract_flat": True,
        "no_warnings": True,
        "quiet": True,
    }

    def __init__(self, url):
        super(YtbInfo, self).__init__()

        self.url = url
        self.ext_url = None

        self.title = None
        self.id = None

        self.entry_titles = []
        self.entry_ids = []

        self.start()

    def run(self):
        try:
            with yt_dlp.YoutubeDL(YtbInfo.OPTS) as ydl:
                result = ydl.extract_info(self.url, download=False)
        except:
            pass
        else:
            self.set_ext_url(result.get("extractor"))
            self.title = result.get("title")

            if "entries" in result and self.ext_url:
                for entry in result["entries"]:
                    self.entry_ids.append(entry.get("id"))
                    self.entry_titles.append(entry.get("title"))

                if None in self.entry_ids:
                    self.id = result.get("id")
                    return

                if None in self.entry_titles:
                    info_list = []
                    for entry_id in self.entry_ids:
                        info_list.append(YtbInfo(self.ext_url + entry_id))

                    for info in info_list:
                        info.wait()

                    self.entry_titles = [info.title for info in info_list]

            else:
                self.id = result.get("id")

    def set_ext_url(self, extractor):
        if not extractor:
            return

        if extractor.startswith("youtube"):
            self.ext_url = "https://youtu.be/"
        
        elif extractor.startswith("vimeo"):
            self.ext_url = "https://vimeo.com/"


class YtbDl(QThread):

    VERSION = "0.0.2"

    OUTPUT_FORMAT = [
        "default",
        "video+audio",
        "audio_only",
    ]

    VIDEO = [
        "mp4",
        "mkv", 
    ]

    AUDIO = [
        "m4a",
        "webm",
        "mp3",
        "ogg",
    ]

    RESOLUTION = [
        "2160p",
        "1440p",
        "1080p",
        "720p",
        "480p",
        "360p",
    ]

    WIDTH = {
        "2160p": "3840",
        "1440p": "2560",
        "1080p": "1920",
        "720p": "1280",
        "480p": "854",
        "360p": "640",
    }

    prog_signal = Signal(dict)

    def __init__(self):
        super(YtbDl, self).__init__()

        self.output_path = ""
        self.url_list = []

        self.ytb_info = {}
        self.info_tmp = []

        self.error = []

    def set_ytb_info(self, url_list):
        self.url_list = url_list

        ytb_info_keys = list(self.ytb_info.keys())
        for url in ytb_info_keys:
            if url not in self.url_list:
                self.info_tmp.append(self.ytb_info.pop(url))
        
        ytb_info_keys = list(self.ytb_info.keys())
        for url in self.url_list:
            if url not in ytb_info_keys:
                self.ytb_info[url] = YtbInfo(url)

    def set_opts(self, **info):
        self.opts = {
            "progress_hooks": [self.hook],
            "no_warnings": True,
            "quiet": True,
        }

        fmt_opts = ["best"]
        self.opts["format"] = fmt_opts[0]
        
        if not info:
            return

        out_fmt = info.get("output_format")
        a_fmt = info.get("audio")

        if (out_fmt not in YtbDl.OUTPUT_FORMAT) or (a_fmt not in YtbDl.AUDIO):
            return

        a_ext = a_fmt
        if a_fmt != "m4a":
            a_ext = "webm"

        audio = "bestaudio[ext={}]".format(a_ext)

        if out_fmt == "audio_only":
            fmt_opts.insert(0, audio)

            if a_fmt == "mp3":
                self.opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    }
                ]

            elif a_fmt == "ogg":
                self.opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "vorbis",
                    }
                ]
                self.opts["postprocessor_args"] = [
                    "-c:a", "copy",
                ]

        else:
            v_fmt = info.get("video")
            width = info.get("width")
            hdr = info.get("hdr")
            
            if (v_fmt not in YtbDl.VIDEO
                    or width not in YtbDl.WIDTH.values()
                    or not isinstance(hdr, bool)):
                return

            codec = "vcodec!*=av01"
            v_ext = v_fmt
            if v_fmt != "mp4":
                v_ext = "webm"
                codec = "vcodec!*=vp9.2"

            video = "bestvideo[ext={}][{}][width<={}]".format(v_ext, codec, width)
            fmt_opts.insert(0, "{}+{}".format(video, audio))

            if hdr and v_ext == "webm":
                video = video.replace("!*=", "*=")
                fmt_opts.insert(0, "{}+{}".format(video, audio))
            
            self.opts["merge_output_format"] = v_fmt

        self.opts["format"] = "/".join(fmt_opts)

    def run(self):
        self.canceled = False

        for url in self.url_list:
            self.ytb_info[url].wait()

        while self.info_tmp:
            self.info_tmp.pop(0).wait()

        if not os.path.isdir(self.output_path):
            self.output_path = os.path.dirname(sys.argv[0])

        self.total_len = len(self.url_list)
        
        for i, url in enumerate(self.url_list):
            if self.canceled:
                return

            title = self.ytb_info[url].title
            
            if not title:
                self.error.append(url)
                continue

            self.title_info = "{} (of {})  {:.100}".format(i + 1, self.total_len, title)
            self.entry_info = ""

            ext_url = self.ytb_info[url].ext_url

            self.opts["outtmpl"] = os.path.join(self.output_path, "%(title).100s.%(ext)s")
            
            if self.ytb_info[url].id or (not ext_url):
                with yt_dlp.YoutubeDL(self.opts) as ydl:
                    ydl.download([url])

            else:
                entry_len = len(self.ytb_info[url].entry_ids)

                for j, entry_id in enumerate(self.ytb_info[url].entry_ids):
                    if self.canceled:
                        return

                    entry = self.ytb_info[url].entry_titles[j]
                    self.entry_info = "{} (of {})  {:.100}".format(j + 1, entry_len, entry)

                    try:
                        entry_dir = re.sub(r'[\\/:*?"<>|]', '', title)
                        entry_path = os.path.join(self.output_path, entry_dir)

                        if not os.path.exists(entry_path):
                            os.mkdir(entry_path)
                    except:
                        pass
                    else:
                        self.opts["outtmpl"] = os.path.join(entry_path, "%(title).100s.%(ext)s")

                    with yt_dlp.YoutubeDL(self.opts) as ydl:
                        ydl.download([ext_url + entry_id])

    def hook(self, data):
        if data["status"] == "downloading":
            info = {
                "title": self.title_info,
                "entry": self.entry_info,
                "per": float(data["_percent_str"][:-1]),
            }

            self.prog_signal.emit(info)


class CustomProgressDialog(QProgressDialog):

    STYLE_SHEET = """
        QProgressDialog QProgressBar {
            border: 1px solid grey;
            border-radius: 2px;
            text-align: center;
        }
        QProgressDialog QProgressBar::chunk {
            border-top-left-radius: 2px;
            border-bottom-left-radius: 2px;
            background-color: QLinearGradient(%s);
        }
    """ % "x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #e7f4ff, stop: 1 #3c94de"

    def __init__(self, parent=None):
        super(CustomProgressDialog, self).__init__(parent)

        self.setWindowTitle("Progress Dialog")
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)
        self.setCancelButtonText("Cancel")
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setWindowModality(Qt.WindowModal)
        self.setStyleSheet(CustomProgressDialog.STYLE_SHEET)


class InfoMessageBox(QMessageBox):

    def __init__(self, parent=None, title="", text=""):
        super(InfoMessageBox, self).__init__(parent)

        self.setWindowTitle(title)
        self.setIcon(QMessageBox.Information)
        self.setStandardButtons(QMessageBox.Ok)
        self.setText(text)

        label = self.layout().itemAt(2).widget()
        label_width = label.sizeHint().width()
        if label_width < 300:
            label_width = 300
        label.setMinimumWidth(label_width)


class YtbDlUi(QWidget):

    TITLE = "youtube-dl UI"

    TEXT_EDIT_STYLE_SHEET = """
        QPlainTextEdit {
            background-color: %s;
            border: 1px solid %s;
            border-radius: 3px;
        }
        QPlainTextEdit:focus {
            border: 1px solid %s;
            border-radius: 3px;
        }
    """

    def __init__(self):
        super(YtbDlUi, self).__init__()

        print("{} v{}".format(YtbDlUi.TITLE, YtbDl.VERSION), end="\n"*3)

        self.ytb_dl = YtbDl()
        self.ytb_dl.prog_signal.connect(self.update_progress_dialog)
        self.ytb_dl.finished.connect(self.on_thread_finished)

        self.settings = QSettings("abc11010xyz", "youtubedlui")

        self.cleanup_temp()

        self.setWindowTitle(YtbDlUi.TITLE)
        self.resize(534, 350)

        self.init_ui()
        self.init_settings()

    def init_ui(self):
        # WIDGET
        base_color = self.palette().base().color().name()
        dark_color = self.palette().dark().color().name()

        self.text_edit = QPlainTextEdit()
        self.text_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text_edit.setStyleSheet(
            YtbDlUi.TEXT_EDIT_STYLE_SHEET % (base_color, dark_color, "#41adff")
        )

        self.download_btn = QPushButton("download")
        self.download_btn.setFixedHeight(32)

        self.path_le = QLineEdit()

        self.file_dialog_btn = QPushButton("...")
        self.file_dialog_btn.setFixedSize(30, 22)
        self.file_dialog_btn.setStyleSheet("padding-right: -2px;")

        self.format_cb = QComboBox()
        self.format_cb.setObjectName("output_format")
        self.format_cb.addItems(YtbDl.OUTPUT_FORMAT)

        self.video_cb = QComboBox()
        self.video_cb.setObjectName("video")

        self.audio_cb = QComboBox()
        self.audio_cb.setObjectName("audio")

        self.resolution_cb = QComboBox()
        self.resolution_cb.setObjectName("resolution")

        self.hdr_chb = QCheckBox("HDR")
        self.hdr_chb.setObjectName("hdr")

        # LAYOUT
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Save to"))
        path_layout.addWidget(self.path_le)
        path_layout.addWidget(self.file_dialog_btn)
        path_layout.setSpacing(3)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Format"))
        format_layout.addWidget(self.format_cb)
        format_layout.setSpacing(3)

        self.default_disabled_layouts = []

        video_layout = QHBoxLayout()
        video_layout.addWidget(QLabel("Video"))
        video_layout.addWidget(self.video_cb)
        video_layout.setSpacing(3)
        self.default_disabled_layouts.append(video_layout)

        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(QLabel("Up to"))
        resolution_layout.addWidget(self.resolution_cb)
        resolution_layout.setSpacing(3)
        self.default_disabled_layouts.append(resolution_layout)

        hdr_layout = QHBoxLayout()
        hdr_layout.addWidget(self.hdr_chb)
        self.default_disabled_layouts.append(hdr_layout)

        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel("Audio"))
        audio_layout.addWidget(self.audio_cb)
        audio_layout.setSpacing(3)
        self.default_disabled_layouts.append(audio_layout)

        options_layout = QHBoxLayout()
        options_layout.setContentsMargins(3, 0, 0, 0)
        options_layout.setSpacing(12)
        options_layout.addLayout(format_layout)
        options_layout.addLayout(video_layout)
        options_layout.addLayout(audio_layout)
        options_layout.addLayout(resolution_layout)
        options_layout.addLayout(hdr_layout)
        options_layout.addStretch()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(7)
        main_layout.addWidget(self.text_edit)
        main_layout.addWidget(self.download_btn)
        main_layout.addLayout(path_layout)
        main_layout.addLayout(options_layout)

        # CONNECTION
        self.text_edit.textChanged.connect(self.on_text_edit_changed)
        self.download_btn.clicked.connect(self.on_download_btn_clicked)
        self.file_dialog_btn.clicked.connect(self.on_file_dialog_btn_clicked)
        self.path_le.textChanged.connect(self.on_path_le_changed)

        self.options_signals = [
            self.format_cb.currentTextChanged,
            self.video_cb.currentTextChanged,
            self.audio_cb.currentTextChanged,
            self.resolution_cb.currentTextChanged,
            self.hdr_chb.stateChanged,
        ]

        self.connect_options_signals(True)

    def connect_options_signals(self, conn):
        connection = "connect" if conn else "disconnect"

        for signal in self.options_signals:
            getattr(signal, connection)(self.on_options_changed)

    def block_options_signals(func):
        def wrapper(self, *args, **kwargs):
            self.connect_options_signals(False)
            func(self, *args, **kwargs)
            self.connect_options_signals(True)
        return wrapper

    def on_options_changed(self, data):
        sender = self.sender().objectName()

        if sender == "output_format":
            self.options[sender] = data
        else:
            fmt = self.options["output_format"]
            self.options[fmt][sender] = data

        if sender in ["output_format", "video", "hdr"]:
            self.refresh_options()

        self.settings.setValue("options", self.options)

    def on_text_edit_changed(self):
        url_list = self.text_edit.toPlainText().split()
        self.ytb_dl.set_ytb_info(url_list)

    def on_download_btn_clicked(self):
        if not self.ytb_dl.url_list:
            return

        info = {
            "output_format": self.format_cb.currentText(),
            "audio": self.audio_cb.currentText(),
        }

        if info["output_format"] != "audio_only":
            info["video"] = self.video_cb.currentText()
            info["width"] = YtbDl.WIDTH[self.resolution_cb.currentText()]
            info["hdr"] = bool(self.hdr_chb.checkState())

        self.ytb_dl.set_opts(**info)

        self.show_progress_dialog()

        self.ytb_dl.start()

    def on_file_dialog_btn_clicked(self):
        path = QFileDialog.getExistingDirectory(
            self, "Open Directory", self.settings.value("output_path")
        )

        if path:
            path = os.path.normcase(path)
            self.path_le.setText(path)

    def on_path_le_changed(self, text):
        if os.path.isdir(text):
            self.download_btn.setText("download")
            self.download_btn.setEnabled(True)
            self.settings.setValue("output_path", text)
            self.ytb_dl.output_path = text
        else:
            self.download_btn.setText("directory does not exist")
            self.download_btn.setDisabled(True)

    def init_settings(self):
        self.load_settings()
        self.refresh_options()

    def load_settings(self):
        output_path = self.settings.value("output_path", os.path.dirname(sys.argv[0]))
        self.path_le.setText(output_path)

        default_options = {
            "output_format": "default",
            "default": {
                "video": "mp4",
                "audio": "m4a",
                "resolution": "1080p",
                "hdr": 0,
            },
            "video+audio": {
                "video": "mp4",
                "audio": "m4a",
                "resolution": "1080p",
                "hdr": 0,
            },
            "audio_only": {
                "audio": "m4a",
                "hdr": 0,
            },
        }
        self.options = self.settings.value("options", default_options)

    def refresh_options(self):
        self.refresh_options_items()
        self.refresh_options_states()
    
    @block_options_signals
    def refresh_options_items(self):
        fmt = self.options["output_format"]
        hdr = self.options[fmt]["hdr"]

        self.format_cb.setCurrentText(fmt)
        self.hdr_chb.setChecked(hdr)

        self.video_cb.clear()
        self.audio_cb.clear()
        self.resolution_cb.clear()

        if fmt == "audio_only":
            self.audio_cb.addItems(YtbDl.AUDIO)
        else:
            self.video_cb.addItems(YtbDl.VIDEO)
            self.audio_cb.addItems(YtbDl.AUDIO[:2])
            self.resolution_cb.addItems(YtbDl.RESOLUTION)

            video = self.options[fmt]["video"]
            resolution = self.options[fmt]["resolution"]

            self.video_cb.setCurrentText(video)
            self.resolution_cb.setCurrentText(resolution)

            if hdr:
                self.video_cb.setCurrentText("mkv")
            else:
                if video == "mp4":
                    if resolution in YtbDl.RESOLUTION[:2]:
                        self.resolution_cb.setCurrentText(YtbDl.RESOLUTION[2])
                    
                    for i in range(2):
                        self.resolution_cb.removeItem(0)

                    self.audio_cb.setCurrentText("m4a")
                    return

        self.audio_cb.setCurrentText(self.options[fmt]["audio"])

    def refresh_options_states(self):
        fmt = self.options["output_format"]

        self.set_child_widget_disabled(self.default_disabled_layouts, False)

        if fmt == "default":
            self.set_child_widget_disabled(self.default_disabled_layouts, True)
            
        elif fmt == "audio_only":
            self.set_child_widget_disabled(self.default_disabled_layouts[:-1], True)
        
        else:
            if self.options[fmt]["hdr"]:
                self.set_child_widget_disabled(self.default_disabled_layouts[:1], True)
            else:
                if self.options[fmt]["video"] == "mp4":
                    self.set_child_widget_disabled(self.default_disabled_layouts[-1:], True)

    def set_child_widget_disabled(self, layouts, disabled):
        for layout in layouts:
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if widget is not None:
                    widget.setDisabled(disabled)

    def show_progress_dialog(self):
        self.prog_label_text = "please wait..."
        self.prog_label = QLabel(self.prog_label_text)
        self.prog_label.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
        self.prog_label.setStyleSheet("padding-top: 10px;")

        self.progress = CustomProgressDialog(self)
        self.progress.setFixedSize(600, 150)
        self.progress.setRange(0, 0)
        self.progress.setLabel(self.prog_label)
        self.progress.canceled.connect(self.on_progress_canceled)
        self.progress.show()

    def update_progress_dialog(self, info):
        QApplication.processEvents()

        if self.ytb_dl.canceled:
            self.progress.setLabelText(self.prog_label_text)
            self.prog_label.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
            self.progress.setRange(0, 0)
        else:
            text = "{}\n{}".format(info["title"], info["entry"])
            self.progress.setLabelText(text)
            self.prog_label.setAlignment(Qt.AlignVCenter)
            self.progress.setRange(0, 100)

        self.progress.setValue(info["per"])

    def on_progress_canceled(self):
        if self.ytb_dl.isRunning():
            self.ytb_dl.canceled = True
            self.progress.show()
    
    def on_thread_finished(self):
        self.progress.close()

        if not self.ytb_dl.canceled:
            self.text_edit.clear()
            self.show_info_dialog()

    def show_info_dialog(self):
        total_len = self.ytb_dl.total_len
        error_len = len(self.ytb_dl.error)

        msg = "{} (of {}) URL(s)".format(total_len - error_len, total_len)
        msg = "::: Download Completed :::\n{}".format(msg)
        error = ""

        if self.ytb_dl.error:
            error = "\n".join(self.ytb_dl.error)
            error = "::: Error :::\n{}".format(error)

            if total_len == error_len:
                msg = ""
            else:
                error = "\n"*2 + error

        text = msg + error + "\n"

        self.ytb_dl.error = []

        msg_box = InfoMessageBox(self, "Info", text)
        msg_box.exec_()

    def cleanup_temp(self):
        temp = self.settings.value("temp", "")
        
        if os.path.exists(temp):
            try:
                shutil.rmtree(temp)
            except:
                pass

        self.settings.setValue("temp", getattr(sys, "_MEIPASS", ""))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    ytb_dl_ui = YtbDlUi()
    ytb_dl_ui.show()
    sys.exit(app.exec_())