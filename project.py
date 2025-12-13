import streamlit as st
import speech_recognition as sr
import requests
from pypdf import PdfReader
from docx import Document
from PIL import Image
import numpy as np
import easyocr

st.set_page_config (
    page_title="CODE GENIE",
    page_icon = "CG",
    layout="centered",
    initial_sidebar_state="expanded"
)
# --- OLLAMA API URL ---
url = "http://localhost:11434/api/chat"

# --- LOAD OCR (EasyOCR only) ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

ocr_reader = load_ocr()

from callbacks import (
    handle_new_chat_click,
    toggle_upload,
    toggle_mic,
    handle_query_submit,
    load_chat
)
from styles import inject_css

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="CodeGenie",
    layout="centered",
    initial_sidebar_state="auto"
)

# --- SESSION STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_started" not in st.session_state:
    st.session_state.chat_started = False
if "upload_clicked" not in st.session_state:
    st.session_state.upload_clicked = False
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None
if "mic_active" not in st.session_state:
    st.session_state.mic_active = False
if "input_key" not in st.session_state:
    st.session_state.input_key = 0
if "recent_chats" not in st.session_state:
    st.session_state.recent_chats = []
if "listening" not in st.session_state:
    st.session_state.listening = False

# --- VOICE INPUT ---
def capture_voice_input():
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        if st.session_state.listening:
            st.info("🎙️ Listening... Speak now!")
            audio_data = recognizer.listen(source)
            st.session_state.audio = audio_data
        else:
            if "audio" in st.session_state:
                st.info("⏳ Processing your voice...")
                audio_data = st.session_state.audio
                st.session_state.audio = not st.session_state.audio

                try:
                    text = recognizer.recognize_google(audio_data)
                    st.success(f"✅ You said: {text}")
                    return text
                except sr.UnknownValueError:
                    st.warning("❌ Sorry, I couldn't understand your speech.")
                    return ""
                except sr.RequestError as e:
                    st.error(f"⚠️ Could not request results; {e}")
                    return ""

# --- TEXT EXTRACTION FROM FILES ---
def extract_text_from_file(uploaded_file):
    file_type = uploaded_file.type
    extracted_text = ""

    try:
        # Images
        if file_type.startswith("image/"):
            image = Image.open(uploaded_file)
            image_np = np.array(image)
            extracted_text = "".join(ocr_reader.readtext(image_np, detail=0))

        # PDF
        elif file_type == "application/pdf":
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                extracted_text += page.extract_text() or ""

        # DOCX
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = Document(uploaded_file)
            extracted_text = "\n".join(para.text for para in doc.paragraphs)

        # TXT
        elif file_type == "text/plain":
            extracted_text = uploaded_file.read().decode("utf-8")

        else:
            st.warning("Unsupported file type. Please upload image, PDF, or text document.")
            return ""

        return extracted_text.strip()

    except Exception as e:
        st.error(f"❌ Error reading file: {e}")
        return ""

# --- SIDEBAR ---
def render_sidebar():
    with st.sidebar:
        st.button(
            "➕ New Chat",
            on_click=handle_new_chat_click,
            key="new_chat_button",
            use_container_width=True
        )

        st.markdown("<h3>💬 Recent chats</h3>", unsafe_allow_html=True)

        for i, chat in enumerate(st.session_state.recent_chats):
            st.button(
                chat["title"],
                on_click=load_chat,
                args=(i,),
                key=f"chat_load_btn_{i}",
                use_container_width=True
            )

        st.markdown("""
            <div class="profile">
                <div class="avatar">CG</div>
                <div class="details">
                    <div class="name">Code Genie</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

# --- CHAT HISTORY ---
def render_chat_history():
    chat_history_class = "chat-history-container visible" if st.session_state.chat_started else "chat-history-container"

    st.markdown(f'<div class="{chat_history_class}">', unsafe_allow_html=True)

    for message in st.session_state.messages:
        role = message["role"]
        content = message["content"]

        row_class = "chat-message-row user-message-row" if role == "user" else "chat-message-row ai-message-row"
        bubble_class = "chat-message-bubble user-message-bubble" if role == "user" else "chat-message-bubble ai-message-bubble"

        st.markdown(
            f"""
            <div class="{row_class}">
                <div class="{bubble_class}">
                    {content}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown('</div>', unsafe_allow_html=True)

# --- INPUT AREA ---
def render_input_area():
    search_bar_class = "search-bar-container fixed-bottom" if st.session_state.chat_started else "search-bar-container"

    st.markdown(f'<div class="{search_bar_class}">', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 10, 1])
    current_input_key = f"query_input_value_{st.session_state.input_key}"

    with col1:
        st.button("➕", on_click=toggle_upload, key=f"plus_button_{st.session_state.input_key}")

    with col2:
        user_input = st.text_area(
            label="chat_input",
            placeholder="Message CodeGenie...",
            height=52,
            max_chars=2000,
            key=current_input_key,
            label_visibility="collapsed"
        )

    with col3:
        mic_icon = "🎙️" if st.session_state.get("mic_active", False) else "🎤"
        st.button(mic_icon, on_click=toggle_mic, key=f"mic_button_{st.session_state.input_key}")

    # Voice input
    if st.session_state.get("mic_active", False):
        st.session_state.listening = not st.session_state.listening
        voice_text = capture_voice_input()
        if voice_text:
            user_input = voice_text
            st.session_state.mic_active = False

    st.markdown('</div>', unsafe_allow_html=True)

    # Send message
    if user_input and user_input.strip():
        st.session_state.chat_started = True
        st.session_state.messages.append({"role": "user", "content": user_input})

        payload = {
            "model": "CodeGenie",
            "messages": st.session_state.messages,
            "stream": False
        }

        try:
            response = requests.post(url, json=payload).json()
            assistant_msg = response["message"]["content"]
            st.session_state.messages.append({"role": "assistant", "content": assistant_msg})

        except Exception as e:
            st.error(f"Error contacting Ollama: {e}")
        
        st.session_state.input_key += 1
        st.rerun()

# --- FILE UPLOADER ---
def render_file_uploader():
    if st.session_state.upload_clicked and st.session_state.uploaded_file is None:
        st.markdown('<div class="file-uploader-fixed">', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "Upload your file",
            key="file_uploader_main",
            type=["pdf", "png", "jpg", "jpeg", "txt", "docx"],
            label_visibility="visible"
        )

        if uploaded_file:
            st.session_state.uploaded_file = uploaded_file
            st.toast(f"✅ Uploaded: {uploaded_file.name}")

            extracted_text = extract_text_from_file(uploaded_file)

            if extracted_text:
                st.session_state.chat_started = True
                st.session_state["ocr_text"] = extracted_text

                preview = extracted_text[:500]

                st.session_state.messages.append({
                    "role": "user",
                    "content": f"📎 Extracted text from {uploaded_file.name}:\n\n{preview}"
                })

                with st.expander("Show Full Extracted Text"):
                    st.text_area("Extracted Text", extracted_text, height=300)

                payload = {
                    "model": "CodeGenie",
                    "messages": st.session_state.messages,
                    "temperature": 1,
                    "max_tokens_to_sample": 300,
                    "stream": False
                }

                try:
                    response = requests.post(url, json=payload).json()
                    assistant_msg = response["message"]["content"]
                    st.session_state.messages.append({"role": "assistant", "content": assistant_msg})

                except Exception as e:
                    st.error(f"Error contacting Ollama: {e}")
                
                st.session_state.upload_clicked = False
                st.session_state.input_key += 1
                st.rerun()
                
        st.markdown('</div>', unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    inject_css()
    
    # Title - only show when chat hasn't started
    if not st.session_state.chat_started:
        st.markdown('<h1 class="title">What can I help with?</h1>', unsafe_allow_html=True)
    else:
        st.markdown('<h1 class="title hidden">What can I help with?</h1>', unsafe_allow_html=True)

    render_chat_history()
    render_file_uploader()
    render_input_area()
    render_sidebar()

if __name__ == "__main__":
    main()