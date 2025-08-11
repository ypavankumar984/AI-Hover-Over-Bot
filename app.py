import sys
import os
import pytesseract
from PIL import ImageGrab
import google.generativeai as genai
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QScrollArea, QTextEdit,
    QPushButton, QLineEdit, QHBoxLayout, QLabel, QSizePolicy,
    QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject
import pyttsx3
import speech_recognition as sr
from dotenv import load_dotenv

load_dotenv()

tess_path = os.getenv("TESSERACT_PATH")
if tess_path:
    pytesseract.pytesseract.tesseract_cmd = tess_path

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Initialize TTS engine globally
tts_engine = pyttsx3.init()
tts_engine.setProperty('rate', 160)

class OCRWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, question):
        super().__init__()
        self.question = question.strip()

    def run(self):
        try:
            screenshot = ImageGrab.grab()
            extracted_text = pytesseract.image_to_string(screenshot)

            if not extracted_text.strip():
                self.finished.emit("No readable text found on screen.")
                return

            model = genai.GenerativeModel("gemini-1.5-flash")

            if self.question:
                prompt = (
                    f"Screen text:\n{extracted_text}\n\n"
                    f"User question:\n{self.question}\n\n{os.getenv("PROMPT")}"
                )
            else:
                prompt = (
                    f"Screen text:\n{extracted_text}\n\n"
                    f"Provide a useful summary or info about this screen text{os.getenv("PROMPT")}"
                )

            response = model.generate_content(prompt)
            self.finished.emit(response.text)

        except Exception as e:
            self.finished.emit(f"Error: {str(e)}")

class ChatBubble(QLabel):
    def __init__(self, text, is_user=False):
        super().__init__(text)
        self.setWordWrap(True)
        self.is_user = is_user
        self.setStyleSheet(self.get_style())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMaximumWidth(400)
        self.setMargin(10)

    def get_style(self):
        if self.is_user:
            return """
                background-color: #4f46e5;
                color: white;
                border-radius: 15px 15px 0 15px;
                padding: 10px;
                font-size: 14px;
            """
        else:
            return """
                background-color: #e5e7eb;
                color: #111827;
                border-radius: 15px 15px 15px 0;
                padding: 10px;
                font-size: 14px;
            """

class FloatingChatbot(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("🤖 AI Chatbot")
        self.setGeometry(100, 100, 530, 420)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet("""
            background-color: #c7d2fe;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #222;
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        # Header with close button
        header_layout = QHBoxLayout()
        header_label = QLabel("🤖 AI Chatbot")
        header_label.setStyleSheet("font-weight: bold; font-size: 18px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            background: transparent;
            font-size: 18px;
            font-weight: bold;
            color: #444;
        """)
        close_btn.clicked.connect(self.close)
        close_btn.setCursor(Qt.PointingHandCursor)
        header_layout.addWidget(close_btn)
        main_layout.addLayout(header_layout)

        # Scroll area for chat bubbles
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area_widget = QWidget()
        self.chat_area = QVBoxLayout(self.scroll_area_widget)
        self.chat_area.setContentsMargins(10, 10, 10, 10)
        self.chat_area.setSpacing(8)
        self.scroll_area.setWidget(self.scroll_area_widget)
        main_layout.addWidget(self.scroll_area)

        # Input layout
        input_layout = QHBoxLayout()

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask something about current screen...")
        self.input_box.setStyleSheet("""
            padding: 8px;
            font-size: 14px;
            border: 1px solid #a5b4fc;
            border-radius: 8px;
        """)
        self.input_box.returnPressed.connect(self.send_question)
        input_layout.addWidget(self.input_box)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(36, 36)
        self.mic_btn.setStyleSheet("""
            font-size: 20px;
            border-radius: 18px;
            background-color: #e0e7ff;
            border: 1px solid #a5b4fc;
        """)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.clicked.connect(self.toggle_listening)
        input_layout.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet("""
            background-color: #4f46e5;
            color: white;
            padding: 8px 20px;
            border-radius: 8px;
            font-weight: bold;
        """)
        self.send_btn.clicked.connect(self.send_question)
        input_layout.addWidget(self.send_btn)

        main_layout.addLayout(input_layout)

        # Voice output toggle button
        self.voice_output_enabled = True
        self.voice_toggle_btn = QPushButton("🔊 Voice Output: ON")
        self.voice_toggle_btn.setCheckable(True)
        self.voice_toggle_btn.setChecked(True)
        self.voice_toggle_btn.setStyleSheet("""
            background-color: #2563eb;
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: bold;
            margin-top: 8px;
        """)
        self.voice_toggle_btn.clicked.connect(self.toggle_voice_output)
        main_layout.addWidget(self.voice_toggle_btn)

        # Capture screen button
        self.capture_btn = QPushButton("📸 Capture Screen & Summarize")
        self.capture_btn.setStyleSheet("""
            background-color: #2563eb;
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: bold;
            margin-top: 8px;
        """)
        self.capture_btn.clicked.connect(self.capture_and_ask)
        main_layout.addWidget(self.capture_btn)

        self.setLayout(main_layout)

        self.worker = None
        self.listening = False
        self.recognizer = sr.Recognizer()
        self.mic = sr.Microphone()
        self.listen_thread = None

        # Welcome message
        self.add_ai_message("Hello! Ask me about your screen or capture for a summary.")

        # To hold the "Thinking..." bubble
        self.thinking_bubble = None

    def add_ai_message(self, text):
        bubble = ChatBubble(text, is_user=False)
        self.chat_area.addWidget(bubble)
        QTimer.singleShot(50, self.scroll_to_bottom)

    def add_user_message(self, text):
        bubble = ChatBubble(text, is_user=True)
        self.chat_area.addWidget(bubble)
        QTimer.singleShot(50, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def send_question(self):
        question = self.input_box.text().strip()
        if not question:
            self.add_ai_message("⚠️ Please type a question!")
            return
        self.add_user_message(question)
        self.input_box.clear()
        self.start_worker(question)

    def capture_and_ask(self):
        self.add_ai_message("🔍 Capturing screen & summarizing...")
        self.start_worker("")

    def start_worker(self, question):
        if self.worker and self.worker.isRunning():
            self.add_ai_message("⏳ Please wait for previous response...")
            return

        # Thinking bubble
        if self.thinking_bubble is None:
            self.thinking_bubble = ChatBubble("🤔 Thinking...", is_user=False)
            self.chat_area.addWidget(self.thinking_bubble)
        else:
            self.thinking_bubble.setText("🤔 Thinking...")
        QTimer.singleShot(50, self.scroll_to_bottom)

        self.worker = OCRWorker(question)
        self.worker.finished.connect(self.display_response)
        self.worker.start()

    def display_response(self, text):
        if self.thinking_bubble:
            self.thinking_bubble.setText(f"🤖 AI: {text}")
            self.thinking_bubble = None
        else:
            self.add_ai_message(text)
        QTimer.singleShot(50, self.scroll_to_bottom)

        # Text-to-speech if enabled
        if self.voice_output_enabled:
            try:
                tts_engine.say(text)
                tts_engine.runAndWait()
            except Exception as e:
                print("TTS Error:", e)

    def toggle_listening(self):
        if not self.listening:
            self.start_listening()
        else:
            self.stop_listening()

    def start_listening(self):
        self.listening = True
        self.mic_btn.setText("🛑")
        self.add_ai_message("🎙️ Listening...")
        QApplication.processEvents()

        self.listen_thread = QThread()
        self.listen_worker = VoiceListener(self.recognizer, self.mic)
        self.listen_worker.moveToThread(self.listen_thread)

        self.listen_thread.started.connect(self.listen_worker.listen)
        self.listen_worker.finished.connect(self.process_voice_result)
        self.listen_worker.finished.connect(self.listen_thread.quit)
        self.listen_worker.finished.connect(self.listen_worker.deleteLater)
        self.listen_thread.finished.connect(self.listen_thread.deleteLater)
        self.listen_thread.start()

    def stop_listening(self):
        self.listening = False
        self.mic_btn.setText("🎤")

    def process_voice_result(self, result):
        self.add_ai_message("🎙️ Listening stopped.")
        if isinstance(result, Exception):
            self.add_ai_message(f"⚠️ Voice error: {result}")
        else:
            self.add_user_message(result)
            self.start_worker(result)
        self.stop_listening()

    def toggle_voice_output(self):
        self.voice_output_enabled = not self.voice_output_enabled
        if self.voice_output_enabled:
            self.voice_toggle_btn.setText("🔊 Voice Output: ON")
        else:
            self.voice_toggle_btn.setText("🔇 Voice Output: OFF")
            tts_engine.stop()

    def closeEvent(self, event):
        # Stop any ongoing TTS on close
        try:
            tts_engine.stop()
        except:
            pass
        # Stop listening thread if running
        if self.listening and self.listen_thread is not None:
            self.listen_thread.quit()
            self.listen_thread.wait()
        event.accept()

class VoiceListener(QObject):
    finished = pyqtSignal(object)

    def __init__(self, recognizer, mic):
        super().__init__()
        self.recognizer = recognizer
        self.mic = mic

    def listen(self):
        try:
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.listen(source)
            text = self.recognizer.recognize_google(audio)
            self.finished.emit(text)
        except Exception as e:
            self.finished.emit(e)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bot = FloatingChatbot()
    bot.show()
    sys.exit(app.exec_())
