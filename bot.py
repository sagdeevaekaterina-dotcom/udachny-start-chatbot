import json
import os
import time
import random
import re
from datetime import datetime

LOG_FILE = "bot_log.json"

# === БАЗА ЗНАНИЙ И РАСПИСАНИЕ ===
SCHEDULE = {
    "история": {"days": ["вторник", "пятница"], "time": "16:00"},
    "математика": {"days": ["понедельник", "суббота"], "time": "17:00"},
    "русский язык": {"days": ["среда", "четверг"], "time": "18:00"}
}

# 🆕 СЛОВАРЬ ВСЕХ ФОРМ СЛОВ (чтобы бот понимал падежи)
COURSE_SYNONYMS = {
    "история": ["история", "истории", "историю", "историей", "историей", "исторический", "исторические"],
    "математика": ["математика", "математику", "математики", "математикой", "математический", "мат", "матем"],
    "русский язык": ["русский", "русского", "русскому", "русским", "русском", "русский язык", "русского языка", "русскому языку", "русским языком", "русском языке", "русский"]
}

COURSES_INFO = (
    "Школа «Удачный старт» готовит к ЕГЭ и ОГЭ на максимальные баллы!\n"
    "Мы предлагаем курсы по трем направлениям:\n"
    "📜 История\n📐 Математика\n📚 Русский язык\n"
    "Напишите «Записаться на [предмет]», чтобы начать."
)

# 🆕 ФУНКЦИЯ: Ищет в сообщении название предмета (в любой форме)
def find_course_in_text(text):
    text_lower = text.lower()
    for course_name, synonyms in COURSE_SYNONYMS.items():
        for synonym in synonyms:
            if synonym in text_lower:
                return course_name
    return None

# Хранилище сессий пользователей
user_sessions = {}

def get_session(session_id):
    if session_id not in user_sessions:
        user_sessions[session_id] = {"state": "IDLE", "course": None, "chosen_day": None, "name": None, "phone": None}
    return user_sessions[session_id]

def process_message(user_message, session_id="default_user"):
    start_time = time.time()
    session = get_session(session_id)
    msg_lower = user_message.lower()
    
    intent = "unknown"
    response_text = ""
    confidence = 0.0
    is_success = False

    # Если пользователь уже в процессе записи
    if session["state"] == "ASKING_TIME":
        course = session["course"]
        valid_days = SCHEDULE[course]["days"]
        if any(day in msg_lower for day in valid_days):
            chosen_day = next(day for day in valid_days if day in msg_lower)
            session["chosen_day"] = chosen_day
            session["state"] = "ASKING_NAME"
            response_text = "Отличный выбор! Как к вам можно обращаться? (Введите ваше имя)"
            intent = "provide_time_slot"
            confidence = 0.95
            is_success = True
        else:
            days_str = " или ".join(valid_days)
            response_text = f"Пожалуйста, выберите один из доступных дней: {days_str}."
            intent = "invalid_time_slot"
            is_success = False

    elif session["state"] == "ASKING_NAME":
        if len(msg_lower) > 1 and not msg_lower.isdigit():
            session["name"] = user_message.strip().title()
            session["state"] = "ASKING_PHONE"
            response_text = f"Приятно познакомиться, {session['name']}! Укажите ваш номер телефона (например, +79991234567)."
            intent = "provide_name"
            confidence = 0.95
            is_success = True
        else:
            response_text = "Пожалуйста, введите корректное имя."
            intent = "invalid_name"
            is_success = False

    elif session["state"] == "ASKING_PHONE":
        if re.search(r'\+?\d{10,12}', user_message):
            session["phone"] = user_message.strip()
            session["state"] = "IDLE"
            response_text = (
                f"✅ Спасибо, {session['name']}! Вы успешно записаны на курс «{session['course'].title()}» "
                f"на {session['chosen_day']} в {SCHEDULE[session['course']]['time']}.\n"
                f"Ваш номер {session['phone']} сохранён."
            )
            intent = "registration_complete"
            confidence = 1.0
            is_success = True
            session["course"] = None
            session["chosen_day"] = None
            session["name"] = None
            session["phone"] = None
        else:
            response_text = "Похоже, номер телефона введен некорректно. Попробуйте еще раз (например, +79990000000)."
            intent = "invalid_phone"
            is_success = False

    else:
        # Приветствие
        if any(word in msg_lower for word in ["привет", "здравствуйте", "добрый день", "хай"]):
            intent = "greet"
            response_text = "Здравствуйте! Я чат-бот школы «Удачный старт». Я могу рассказать о курсах, показать расписание или записать вас на занятие. Чем помочь?"
            confidence = 0.99
            is_success = True

        # Прощание / Спасибо
        elif any(word in msg_lower for word in ["спасибо", "благодарю"]):
            intent = "thank_you"
            response_text = "Рад был помочь!"
            confidence = 0.99
            is_success = True
        elif any(word in msg_lower for word in ["пока", "до свидания", "бай"]):
            intent = "goodbye"
            response_text = "До свидания! Желаем удачного старта на экзаменах!"
            confidence = 0.99
            is_success = True

        # Какие курсы есть
        elif any(word in msg_lower for word in ["курс", "направления", "что у вас есть", "предметы"]):
            intent = "ask_courses"
            response_text = COURSES_INFO
            confidence = 0.95
            is_success = True

        # 🆕 Расписание (работает с любой формой слова)
        elif "расписан" in msg_lower or "когда" in msg_lower:
            intent = "ask_schedule"
            found_course = find_course_in_text(msg_lower)  # Используем новую функцию
            if found_course:
                days = " и ".join(SCHEDULE[found_course]["days"])
                time_str = SCHEDULE[found_course]["time"]
                response_text = f"📅 {found_course.title()} проходит по {days} в {time_str}."
            else:
                response_text = "Уточните, пожалуйста, по какому предмету вас интересует расписание? (История, Математика или Русский язык)"
            confidence = 0.90
            is_success = True

        # 🆕 Запись на курс (работает с любой формой слова)
        elif any(word in msg_lower for word in ["запиш", "хочу на", "записаться"]):
            found_course = find_course_in_text(msg_lower)  # Используем новую функцию
            if found_course:
                intent = "register_course"
                session["course"] = found_course
                session["state"] = "ASKING_TIME"
                days = " или ".join(SCHEDULE[found_course]["days"])
                time_str = SCHEDULE[found_course]["time"]
                response_text = f"Отлично! Вам удобнее заниматься в {days} в {time_str}?"
                confidence = 0.95
                is_success = True
            else:
                response_text = "Мы проводим курсы по истории, математике и русскому языку. На какой предмет вы хотите записаться?"
                intent = "register_course_unknown_subject"
                is_success = False

        # 🆕 Если пользователь написал просто название предмета — уточняем
        elif find_course_in_text(msg_lower) is not None:
            found_course = find_course_in_text(msg_lower)
            intent = "ask_about_course"
            response_text = (
                f"Вы упомянули курс «{found_course.title()}». Что вы хотите сделать?\n"
                f"1️⃣ Узнать расписание (напишите «расписание {found_course}»)\n"
                f"2️⃣ Записаться на курс (напишите «записаться на {found_course}»)"
            )
            confidence = 0.85
            is_success = True

        # Fallback (не понял)
        else:
            intent = "unknown"
            response_text = "Извините, я не совсем понял ваш запрос. 🤔 Чтобы решить сложный вопрос, я могу переключить вас на живого менеджера. Напишите «менеджер», если хотите."
            confidence = 0.0
            is_success = False
            if "менеджер" in msg_lower:
                response_text = "👨‍💼 Соединяю с менеджером... Пожалуйста, ожидайте!"

    response_time_ms = int((time.time() - start_time) * 1000)
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "user_message": user_message,
        "intent": intent,
        "is_success": is_success,
        "response_text": response_text,
        "confidence_score": confidence,
        "response_time_ms": response_time_ms
    }
    save_log(log_entry)
    
    return response_text

def save_log(event_data, filename=LOG_FILE):
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    logs = json.load(f)
                    if not isinstance(logs, list): logs = []
                except json.JSONDecodeError:
                    logs = []
        else:
            logs = []
        logs.append(event_data)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка логирования: {e}")

if __name__ == "__main__":
    print("🤖 Чат-бот «Удачный старт» запущен! (Введите 'выход' для завершения)")
    session_id = "test_user_001"
    
    while True:
        user_input = input("\nВы: ")
        if user_input.lower() in ["выход", "exit", "стоп"]:
            break
        
        bot_response = process_message(user_input, session_id)
        print(f"Бот: {bot_response}")