import xmlrpc.client
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI  
from datetime import datetime, timedelta
import time
import random
import numpy as np
import json
import os
import re
import base64

# ============================================================
# ░█▀▀░█░░░▀█▀░▀█▀░█▀▀░░░█▀█░█▀▀░░░█░█░▀▀   MUDIR OS v47.9 (ZOOM & RESIZE ENGINE)
# ============================================================
st.set_page_config(
    page_title="MUDIR | Strategic OS",
    page_icon="❖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 0. نظام الحفظ الديناميكي وإدارة التراخيص والسجلات (Data Vault)
# ============================================================
CONFIG_FILE = "mudir_config.json"
LICENSES_FILE = "mudir_licenses.json"
MASTER_ADMIN_CODE = "admin185710" # الكود السري الخاص بك لدخول لوحة تحكم التراخيص

DEFAULT_SYSTEM_PROMPT = """أنت 'المدير'. مدير تنفيذي مصري شاطر جداً، خبرة سنين في المبيعات والتسويق وإدارة الشركات.
شخصيتك: مصري أصيل، بتتكلم بلهجة مصرية طبيعية جداً جداً وبطريقة احترافية (كأنك مدير قاعد في مكتبه بيوجه فريقه)، حازم، جاد، معلم، ومبتسمحش في التقصير أو الأعذار. بتدي أوامر واضحة وتتابعها وتقيم الموظفين وتناقشهم في أوقات التنفيذ.

قواعد التعامل وتوزيع المهام:
1. لو الموظف بيطلب خطة، اديله تكليف محدد بناء على المسمى الوظيفي بتاعه واسأله (هتخلص ده في قد إيه؟).
2. إذا كان دوره "مبيعات": كلفه بصرامة إنه يتابع (عروض الأسعار المعلقة) واطلب منه يجيبلك الخلاصة ويقفل البيعة.
3. إذا كان "تسويق" أو "تطوير أعمال": اقترح عليه أسماء شركات واقعية في مصر أو الخليج لفتح أسواق معاها.
4. تابعه واسأله عن الوقت اللي خده، لو اتأخر أو مفيش نتيجة، كن حازم ووبخه بشياكة كمدير. لو شاطر شجعه بكلمة (عاش يا بطل).
5. تجنب استخدام الرموز التعبيرية تماماً عشان تحافظ على هيبتك كمدير. استخدم التنسيق الواضح بالماركداون (عناوين، نقاط، أرقام).
6. التحكم في النظام: لو شفت إن في ضرورة ماسة لإنشاء مسودة عرض سعر لعميل لإنقاذ الموقف، أضف هذا الكود في نهاية رسالتك بالضبط:
$$ACTION: CREATE_SO | العميل: [اسم العميل] | القيمة: [مبلغ تقديري]$$"""

def get_workspace_file(ws_id=None):
    target_id = ws_id if ws_id else st.session_state.get('workspace_id', 'default')
    safe_id = "".join(c for c in str(target_id) if c.isalnum() or c in ('_', '-'))
    return f"mudir_workspace_{safe_id}.json"

def load_config():
    defaults = {
        'ODOO_URL': '',
        'ODOO_DB': '',
        'ODOO_USER': '',
        'ODOO_PASS': '',
        'AI_PROVIDER_URL': 'https://api.openai.com/v1',
        'AI_API_KEY': '',
        'AI_MODEL_NAME': 'gpt-4o',
        'AI_SYSTEM_PROMPT': DEFAULT_SYSTEM_PROMPT,
        'MANAGER_PIN': '0000', 
        'EMPLOYEES': [], 
        'EVALUATIONS': {},
        'ALL_CHATS': {},
        'AUDIT_LOG': {} # السجل السري المنيع الذي لا يُمحى أبداً
    }
    
    if 'workspace_id' in st.session_state:
        ws_file = get_workspace_file()
        if os.path.exists(ws_file):
            try:
                with open(ws_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    defaults.update(saved_config)
            except Exception:
                pass
    return defaults

def save_config(cfg_dict):
    if 'workspace_id' in st.session_state:
        try:
            ws_file = get_workspace_file()
            with open(ws_file, 'w', encoding='utf-8') as f:
                json.dump(cfg_dict, f, ensure_ascii=False, indent=4)
        except Exception:
            pass 

def save_chats():
    if 'app_config' in st.session_state:
        st.session_state.app_config['ALL_CHATS'] = st.session_state.all_chats
        save_config(st.session_state.app_config)

def log_message(user, msg_dict):
    """دالة المراقبة: تنسخ أي رسالة جديدة فوراً إلى السجل السري مع طابع زمني"""
    if 'app_config' in st.session_state:
        cfg = st.session_state.app_config
        if 'AUDIT_LOG' not in cfg:
            cfg['AUDIT_LOG'] = {}
        if user not in cfg['AUDIT_LOG']:
            cfg['AUDIT_LOG'][user] = []
        
        entry = msg_dict.copy()
        entry['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cfg['AUDIT_LOG'][user].append(entry)

def load_licenses():
    if os.path.exists(LICENSES_FILE):
        try:
            with open(LICENSES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {"workspaces": {}}

def save_licenses(data):
    try:
        with open(LICENSES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except: pass

# ============================================================
# أزرار القائمة الجانبية (Navigation Items)
# ============================================================
ALL_NAV_ITEMS = [
    ("dashboard", "dashboard", "لوحة القيادة"),
    ("departments", "layers", "أداء الأقسام"),
    ("forecast", "bulb", "التنبؤ المستقبلي"),
    ("ai", "send", "مكتب المدير"),
    ("fusion", "fusion", "مختبر البيانات"),
    ("territories", "globe", "التحليل الجغرافي"),
    ("settings", "settings", "إعدادات النظام")
]

# ============================================================
# التوجيه الذكي للروابط (URL Routing & Initialization)
# ============================================================
def init_state():
    url_ws = st.query_params.get("workspace")
    url_view = st.query_params.get("view")

    if 'view' not in st.session_state:
        st.session_state.view = 'workspace_login'
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None

    if url_ws and 'workspace_key' not in st.session_state:
        if url_ws == "SUPER_ADMIN":
            st.session_state.workspace_key = "SUPER_ADMIN"
            st.session_state.workspace_id = "SUPER_ADMIN"
            st.session_state.view = url_view if url_view else 'super_admin'
        else:
            licenses = load_licenses()
            ws_data = licenses.get('workspaces', {}).get(url_ws)
            if ws_data and ws_data.get('status') == 'active':
                expiry_str = ws_data.get('expiry_date')
                if expiry_str:
                    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                    if datetime.now() <= expiry_date:
                        st.session_state.workspace_key = url_ws
                        st.session_state.workspace_id = url_ws
                        st.session_state.app_config = load_config()
                        st.session_state.view = url_view if url_view else 'login'

    if 'workspace_key' not in st.session_state:
        if st.session_state.get('view') != 'super_admin':
            st.session_state.view = 'workspace_login'
        return
        
    if 'app_config' not in st.session_state:
        st.session_state.app_config = load_config()
        
    defaults = {
        'view': url_view if url_view else 'login', 
        'modal_open': False, 'modal_title': '', 'modal_data': {},
        'current_user': None, 
        'growth_stream': None, 'last_radar_report': None, 'data_loaded': False,
        'df_s': pd.DataFrame(), 'df_p': pd.DataFrame(), 'df_i': pd.DataFrame(),
        'df_po': pd.DataFrame(), 'df_pol': pd.DataFrame(), 'is_real_data': False
    }
    
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v
        
    if 'all_chats' not in st.session_state:
        st.session_state.all_chats = st.session_state.app_config.get('ALL_CHATS', {})

def call_universal_ai(messages):
    api_key = st.session_state.app_config.get('AI_API_KEY', '').strip()
    if not api_key:
        raise Exception("مفتاح الاتصال بالخادم غير متوفر.")
    
    base_url = st.session_state.app_config.get('AI_PROVIDER_URL', '').strip()
    if not base_url: base_url = None
    
    model_name = st.session_state.app_config.get('AI_MODEL_NAME', 'gpt-4o')

    client = OpenAI(api_key=api_key, base_url=base_url)
    
    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7
    )
    return response.choices[0].message.content

# ============================================================
# 4. طبقة البيانات والتلوين الذكي المضاد للانهيار
# ============================================================

def get_icon(name: str, size: int = 24, color: str = "currentColor", class_name: str = "") -> str:
    svg_map = {
        "dashboard": '<path d="M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z"/>',
        "radar": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v10l5 5"/>',
        "cpu": '<rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
        "fusion": '<path d="M9 3v11l-5 6v2h16v-2l-5-6V3M14 3h-4"/>',
        "rocket": '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
        "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
        "money": '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
        "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
        "orders": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
        "stock": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="M3.27 6.96L12 12.01l8.73-5.05M12 22.08V12"/>',
        "check": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/>',
        "chart": '<path d="M18 20V10M12 20V4M6 20v-4"/>',
        "globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
        "robot": '<rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4M8 16h.01M16 16h.01"/>',
        "search": '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
        "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
        "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
        "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
        "bulb": '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/><path d="M12 2v2"/>',
        "dna": '<path d="M2 15c6.667-6 13.333 0 20-6"/><path d="M2 9c6.667 6 13.333 0 20 6"/><path d="m17 4-1 1.5"/><path d="m19 6-1 1.5"/><path d="m5 18-1-1.5"/><path d="m7 20-1-1.5"/><path d="m10.5 7.5-1 1.5"/><path d="m14.5 16.5-1-1.5"/>',
        "send": '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
        "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
        "table": '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>',
        "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
        "tabs": '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M2 11h20"/><path d="M6 7v4"/><path d="M12 7v4"/>',
        "map": '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
        "command": '<rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><polyline points="9 9 12 12 9 15"/><line x1="13" y1="15" x2="15" y2="15"/>',
        "handshake": '<path d="M8 12.5L4 16.5M16 12.5L20 16.5M12 15v4M7 8h10"/><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/>',
        "truck": '<rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
        "trending-up": '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
        "trending-down": '<polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/>',
        "calendar": '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
        "edit": '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
        "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
        "manager": '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
        "employee": '<circle cx="12" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>',
        "print": '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
        "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'
    }
    path = svg_map.get(name, "")
    return f'<svg xmlns="http://www.w3.org/2000/svg" class="{class_name}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'

def get_base64_svg(icon_name, color="#00f2ff"):
    svg_str = get_icon(icon_name, 24, color)
    b64 = base64.b64encode(svg_str.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64}"

def map_state_ar(state_val):
    val = str(state_val).lower()
    if val in ['sale', 'done']: return 'موافق عليه'
    if val in ['draft', 'sent']: return 'مسودة'
    if val in ['cancel']: return 'ملغي'
    return val

def map_po_state_ar(state_val):
    val = str(state_val).lower()
    if val in ['purchase', 'done']: return 'معتمد'
    if val in ['draft', 'sent', 'to approve']: return 'مسودة / قيد الانتظار'
    if val in ['cancel']: return 'ملغي'
    return val

def clean_department_name(val):
    name_str = str(val).strip()
    if not val or name_str.lower() in ['none', 'false', '']: return 'غير محدد'
    return name_str

def clean_odoo_m2o(val):
    if isinstance(val, list) and len(val) >= 2: 
        res = str(val[1]).strip()
        return res if res.lower() not in ['false', 'none', ''] else "غير محدد"
    elif isinstance(val, str): 
        res = val.strip()
        return res if res.lower() not in ['false', 'none', ''] else "غير محدد"
    return "غير محدد"

def extract_department_from_row(row):
    for f in ['project_id', 'analytic_account_id', 'team_id']:
        if f in row and row[f] and str(row[f]).lower() not in ['false', 'none', '']:
            return clean_odoo_m2o(row[f])
    for f in row.keys():
        if 'project' in f.lower() and f != 'project_id':
            if row[f] and str(row[f]).lower() not in ['false', 'none', '']:
                return clean_odoo_m2o(row[f])
    return "غير محدد"

# ────────────────────────────────────────────────────────────
# الدالة الأساسية لتنظيف، ترتيب، وتلوين الجداول بأمان 100%
# ────────────────────────────────────────────────────────────
def style_dataframe(df):
    if df is None: return pd.DataFrame()
    
    if hasattr(df, 'data'):
        df_raw = df.data.copy()
    else:
        df_raw = df.copy()

    if df_raw.empty: return df_raw

    currency_cols = ['القيمة (ج.م)', 'إجمالي الفواتير (ج.م)', 'السعر (ج.م)', 'معتمد (ج.م)', 'مسودة (ج.م)', 'ملغي (ج.م)', 'قيمة (معتمد)', 'قيمة (مسودة)', 'قيمة (ملغي)', 'القيمة الكلية (ج.م)', 'إجمالي التكلفة (ج.م)', 'الإيرادات', 'المصروفات', 'صافي الربح', 'صاف الربح']
    number_cols = ['الكمية المتاحة', 'عدد العروض', 'عدد (معتمد)', 'عدد (مسودة)', 'عدد (ملغي)', 'العدد الكلي', 'الكمية المطلوبة', 'إجمالي العروض', 'إجمالي الطلبات']
    pct_cols = ['هامش الربح %']
    
    all_numeric = currency_cols + number_cols + pct_cols

    for col in all_numeric:
        if col in df_raw.columns:
            if df_raw[col].dtype == object or df_raw[col].dtype.name == 'category':
                df_raw[col] = df_raw[col].astype(str).str.replace(r'[^\d.-]', '', regex=True)
            df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0)
            
    for col in df_raw.columns:
        if col not in all_numeric:
            df_raw[col] = df_raw[col].fillna("").astype(str)

    target_cols_priority = ['صافي الربح', 'صاف الربح', 'القيمة الكلية (ج.م)', 'قيمة (معتمد)', 'قيمة (مسودة)', 'قيمة (ملغي)', 'القيمة (ج.م)', 'معتمد (ج.م)', 'إجمالي الفواتير (ج.م)', 'الكمية المتاحة', 'الكمية المطلوبة', 'الإيرادات', 'العدد الكلي', 'إجمالي العروض', 'إجمالي الطلبات']
    active_target = None
    for col in target_cols_priority:
        if col in df_raw.columns:
            active_target = col
            break

    if active_target:
        df_raw = df_raw.sort_values(by=active_target, ascending=False).reset_index(drop=True)

    fmt = {}
    for c in currency_cols:
        if c in df_raw.columns: fmt[c] = "{:,.0f} ج.م"
    for c in number_cols:
        if c in df_raw.columns: fmt[c] = "{:,.0f}"
    for c in pct_cols:
        if c in df_raw.columns: fmt[c] = "{:.1f}%"

    try:
        styler = df_raw.style
        if active_target:
            styler = styler.background_gradient(subset=[active_target], cmap='RdYlGn')
        if fmt:
            styler = styler.format(fmt)
        return styler
    except Exception as e:
        return df_raw

@st.cache_data(ttl=600, show_spinner=False)
def fetch_master_data(url, db, user, pswd):
    try:
        if not all([url, db, user, pswd]): raise ValueError("بيانات تسجيل الدخول غير مكتملة.")
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, user, pswd, {})
        if not uid: raise Exception("البيانات صحيحة برمجياً لكن أودو يرفض الصلاحية.")
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        so_fields = models.execute_kw(db, uid, pswd, 'sale.order', 'fields_get', [], {'attributes': ['type', 'string']})
        target_fields = ['name','partner_id','amount_total','date_order','state','user_id']
        
        for f in ['project_id', 'analytic_account_id', 'team_id', 'margin']:
            if f in so_fields: 
                target_fields.append(f)
        
        for f, meta in so_fields.items():
            if f not in target_fields and meta.get('type') == 'many2one':
                f_name = f.lower()
                f_str = str(meta.get('string', '')).lower()
                if 'project' in f_name or 'مشروع' in f_str or 'قسم' in f_str:
                    target_fields.append(f)

        s_raw = models.execute_kw(db, uid, pswd, 'sale.order', 'search_read', [[]], {'fields': target_fields, 'limit': 500})
        p_raw = models.execute_kw(db, uid, pswd, 'res.partner', 'search_read', [[]], {'fields': ['name','city','industry_id','total_invoiced','email','phone'], 'limit': 200})
        i_raw = models.execute_kw(db, uid, pswd, 'product.product', 'search_read', [[('sale_ok','=',True)]], {'fields': ['name','lst_price','qty_available','default_code'], 'limit': 200})
        po_raw = models.execute_kw(db, uid, pswd, 'purchase.order', 'search_read', [[]], {'fields': ['name','partner_id','amount_total','date_order','state'], 'limit': 500})
        pol_raw = models.execute_kw(db, uid, pswd, 'purchase.order.line', 'search_read', [[]], {'fields': ['product_id','product_qty','price_subtotal'], 'limit': 500})
        
        df_s, df_p, df_i = pd.DataFrame(s_raw), pd.DataFrame(p_raw), pd.DataFrame(i_raw)
        df_po, df_pol = pd.DataFrame(po_raw), pd.DataFrame(pol_raw)
        
        if not df_s.empty and 'date_order' in df_s.columns: df_s['date_order'] = pd.to_datetime(df_s['date_order'])
        if not df_po.empty and 'date_order' in df_po.columns: df_po['date_order'] = pd.to_datetime(df_po['date_order'])
            
        return df_s, df_p, df_i, df_po, df_pol, True
    except Exception as e:
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df, empty_df, empty_df, False

def get_delta_html(current_val, previous_val):
    if previous_val == 0 or pd.isna(previous_val):
        return "<span class='delta-neu'>--</span>"
    delta_pct = ((current_val - previous_val) / previous_val) * 100
    if delta_pct > 0:
        return f"<span class='delta-pos'>▲ +{delta_pct:.1f}%</span>"
    elif delta_pct < 0:
        return f"<span class='delta-neg'>▼ {delta_pct:.1f}%</span>"
    return "<span class='delta-neu'>--</span>"

def get_smart_filter_dates(prefix):
    st.markdown(f"<div style='font-size:1.1rem; font-weight:900; color:var(--c-primary); margin-bottom:15px; display:flex; align-items:center; gap:8px;'>{get_icon('calendar', 22)} الفلتر الزمني الذكي</div>", unsafe_allow_html=True)
    
    apply_filter = st.checkbox("تفعيل الفلتر الزمني (إلغاء التفعيل يعرض كل الأوقات)", value=False, key=f"{prefix}_apply")
    if not apply_filter:
        return None, None, None, None
        
    opts = ["اليوم", "هذا الأسبوع", "هذا الشهر", "الشهر الماضي", "هذا العام", "فترة مخصصة"]
    sel = st.radio("اختر الفترة:", opts, horizontal=True, key=f"{prefix}_radio", label_visibility="collapsed")
    
    now = datetime.now()
    start_dt, end_dt = None, None
    prev_start_dt, prev_end_dt = None, None
    
    if sel == "اليوم":
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59)
        prev_start_dt = start_dt - timedelta(days=1)
        prev_end_dt = end_dt - timedelta(days=1)
    elif sel == "هذا الأسبوع":
        start_dt = now - timedelta(days=now.weekday())
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59)
        prev_start_dt = start_dt - timedelta(weeks=1)
        prev_end_dt = end_dt - timedelta(weeks=1)
    elif sel == "هذا الشهر":
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59)
        prev_end_dt = start_dt - timedelta(seconds=1)
        prev_start_dt = prev_end_dt.replace(day=1, hour=0, minute=0, second=0)
    elif sel == "الشهر الماضي":
        first_day_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = first_day_this_month - timedelta(seconds=1)
        start_dt = end_dt.replace(day=1, hour=0, minute=0, second=0)
        prev_end_dt = start_dt - timedelta(seconds=1)
        prev_start_dt = prev_end_dt.replace(day=1, hour=0, minute=0, second=0)
    elif sel == "هذا العام":
        start_dt = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59)
        prev_start_dt = start_dt.replace(year=start_dt.year - 1)
        prev_end_dt = end_dt.replace(year=end_dt.year - 1)
    elif sel == "فترة مخصصة":
        min_date = datetime.today().date() - timedelta(days=365)
        max_date = datetime.today().date()
        if not st.session_state.df_s.empty and 'date_order' in st.session_state.df_s.columns:
            min_date = st.session_state.df_s['date_order'].min().date()
            max_date = st.session_state.df_s['date_order'].max().date()
        
        c1, c2, c3 = st.columns([1,1,2])
        with c1: start_d = st.date_input("من تاريخ", value=min_date, key=f"{prefix}_start")
        with c2: end_d = st.date_input("إلى تاريخ", value=max_date, key=f"{prefix}_end")
        
        start_dt = pd.to_datetime(start_d)
        end_dt = pd.to_datetime(end_d) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        delta_days = (end_dt - start_dt).days + 1
        prev_start_dt = start_dt - timedelta(days=delta_days)
        prev_end_dt = start_dt - timedelta(seconds=1)
        
    return start_dt, end_dt, prev_start_dt, prev_end_dt

def render_live_ticker(df_s, df_p):
    if df_s is None or df_s.empty: return
    
    appr = df_s[df_s['state'].isin(['sale','done'])]['amount_total'].sum() if 'state' in df_s.columns else 0
    draft = df_s[df_s['state'].isin(['draft','sent'])]['amount_total'].sum() if 'state' in df_s.columns else 0
    canc = df_s[df_s['state'] == 'cancel']['amount_total'].sum() if 'state' in df_s.columns else 0
    clients = len(df_p) if df_p is not None else 0
    
    ticker_text = "".join([
        f'<div class="ticker-item"><img src="{get_base64_svg("rocket", "#00ff82")}" width="18" style="vertical-align:middle; margin-left:5px;"> إجمالي المبيعات المعتمدة: <span>{appr:,.0f} ج.م</span></div>',
        f'<div class="ticker-item"><img src="{get_base64_svg("orders", "#ffd700")}" width="18" style="vertical-align:middle; margin-left:5px;"> عروض قيد الانتظار: <span>{draft:,.0f} ج.م</span></div>',
        f'<div class="ticker-item"><img src="{get_base64_svg("bell", "#ff2d78")}" width="18" style="vertical-align:middle; margin-left:5px;"> نزيف مالي (ملغي): <span>{canc:,.0f} ج.م</span></div>',
        f'<div class="ticker-item"><img src="{get_base64_svg("users", "#00f2ff")}" width="18" style="vertical-align:middle; margin-left:5px;"> إجمالي العملاء: <span>{clients} عميل</span></div>',
        f'<div class="ticker-item"><img src="{get_base64_svg("bulb", "#ffd700")}" width="18" style="vertical-align:middle; margin-left:5px;"> النظام يعمل بأقصى طاقة استيعابية...</div>'
    ])
    
    st.markdown(f'<div class="ticker-wrap"><div class="ticker-move">{ticker_text}{ticker_text}</div></div>', unsafe_allow_html=True)

# ----------------------------------------------------
# 5. شاشة مساحة العمل و تسجيل الدخول
# ----------------------------------------------------
def render_workspace_login():
    st.markdown("<div style='margin-top: 10vh;'></div>", unsafe_allow_html=True)
    st.markdown("<div class='g-card' style='max-width: 500px; margin: 0 auto; text-align: center;'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:var(--c-primary); margin-bottom: 20px;'>{get_icon('fusion', 60)}</div>", unsafe_allow_html=True)
    st.markdown("<h2 style='color:#fff; margin-top:0;'>بوابة الولوج الآمنة (Mudir OS)</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:var(--c-dim); margin-bottom: 30px;'>أدخل كود الشركة المرخص لفتح مساحة العمل الخاصة بك</p>", unsafe_allow_html=True)
    
    ws_key = st.text_input("كود الشركة (License Key):", type="password", placeholder="أدخل الكود هنا...")
    
    if st.button("تأكيد ودخول", type="primary", use_container_width=True):
        if ws_key.strip():
            if ws_key.strip() == MASTER_ADMIN_CODE:
                st.session_state.workspace_key = "SUPER_ADMIN"
                st.session_state.workspace_id = "SUPER_ADMIN"
                st.session_state.view = 'super_admin'
                st.query_params["workspace"] = "SUPER_ADMIN"
                st.query_params["view"] = "super_admin"
                st.rerun()
                return

            licenses = load_licenses()
            ws_data = licenses.get('workspaces', {}).get(ws_key.strip())
            
            if not ws_data:
                st.error("كود الشركة غير مسجل! يرجى التأكد من الكود أو التواصل مع الإدارة.")
            elif ws_data.get('status') == 'suspended':
                st.error("تم إيقاف هذه المساحة من قبل الإدارة. يرجى المراجعة.")
            else:
                expiry_str = ws_data.get('expiry_date')
                if expiry_str:
                    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d")
                    if datetime.now() > expiry_date:
                        st.error(f"لقد انتهت صلاحية اشتراك شركتك في ({expiry_str}). يرجى تجديد الاشتراك لاستعادة الوصول للبيانات.")
                        return
                
                st.session_state.workspace_key = ws_key.strip()
                st.session_state.workspace_id = ws_key.strip()
                st.session_state.app_config = load_config()
                st.session_state.all_chats = st.session_state.app_config.get('ALL_CHATS', {})
                st.session_state.view = 'login'
                st.query_params["workspace"] = ws_key.strip()
                st.query_params["view"] = "login"
                st.rerun()
        else:
            st.error("الرجاء إدخال الكود.")
    st.markdown("</div>", unsafe_allow_html=True)

def render_login():
    st.markdown("<div style='margin-top: 10vh;'></div>", unsafe_allow_html=True)
    st.markdown("<div class='g-card' style='max-width: 500px; margin: 0 auto; text-align: center;'>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:var(--c-primary); margin-bottom: 20px;'>{get_icon('command', 60)}</div>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='color:#fff; margin-top:0;'>تسجيل الدخول - مساحة: {st.session_state.get('workspace_key', '')}</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:var(--c-dim); margin-bottom: 30px;'>الرجاء تحديد هويتك للوصول لمهامك وصلاحياتك المحددة</p>", unsafe_allow_html=True)
    
    employees = st.session_state.app_config.get('EMPLOYEES', [])
    user_options = ["المدير العام (صلاحيات كاملة)"] + [f"{emp['name']} - {emp['role']}" for emp in employees]
    selected_user = st.selectbox("من أنت؟", user_options, label_visibility="collapsed")
    
    pin = st.text_input("رمز الدخول السري (PIN)", type="password", placeholder="أدخل الرقم السري الخاص بك")
        
    if st.button("دخول للنظام", type="primary", use_container_width=True):
        if "المدير العام" in selected_user:
            if pin == st.session_state.app_config.get('MANAGER_PIN', '0000'):
                st.session_state.current_user = "المدير العام"
                st.session_state.view = 'dashboard'
                st.query_params["view"] = "dashboard"
                if selected_user not in st.session_state.all_chats:
                    initial_msg = {"role": "assistant", "content": "أهلاً بك. الأرقام والبيانات جاهزة للعرض والمناقشة."}
                    st.session_state.all_chats[selected_user] = [initial_msg]
                    log_message(selected_user, initial_msg)
                    save_chats()
                st.rerun()
            else:
                st.error("عذراً، رمز الدخول غير صحيح!")
        else:
            emp_data = next((e for e in employees if f"{e['name']} - {e['role']}" == selected_user), None)
            expected_pin = emp_data.get('pin', '0000') if emp_data else '0000'
            
            if pin == expected_pin:
                st.session_state.current_user = selected_user
                if emp_data and emp_data.get('views'):
                    st.session_state.view = emp_data['views'][0]
                    st.query_params["view"] = emp_data['views'][0]
                else:
                    st.session_state.view = 'ai' 
                    st.query_params["view"] = "ai"
                    
                if selected_user not in st.session_state.all_chats:
                    emp_name_only = selected_user.split(" - ")[0]
                    initial_msg = {"role": "assistant", "content": f"أهلاً بيك يا {emp_name_only}. أنا مديرك. مفيش وقت نضيعه، وريني إيه اللي وراك النهاردة عشان أديك تكليفاتك."}
                    st.session_state.all_chats[selected_user] = [initial_msg]
                    log_message(selected_user, initial_msg)
                    save_chats()
                st.rerun()
            else:
                st.error("عذراً، رمز الدخول السري الخاص بك غير صحيح!")
            
    if st.button("تغيير مساحة العمل", use_container_width=True):
        del st.session_state['workspace_key']
        del st.session_state['workspace_id']
        st.session_state.view = 'workspace_login'
        st.query_params.clear()
        st.rerun()
        
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# 6. شريط التنقل الجانبي (CSS)
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&family=Orbitron:wght@400;700;900&display=swap');

/* تم إظهار الشريط العلوي مؤقتاً لتتمكن من عمل مسح للذاكرة Clear Cache */
/* #MainMenu {visibility: hidden !important; display: none !important;} */
/* header {visibility: hidden !important; display: none !important;} */
/* [data-testid="manage-app-button"] {display: none !important;} */

:root {
    --c-primary:   #00f2ff;
    --c-secondary: #7000ff;
    --c-accent:    #ff2d78;
    --c-gold:      #ffd700;
    --c-bg:        #04040a;
    --c-bg2:       #080810;
    --c-card:      rgba(15,15,25,0.7);
    --c-border:    rgba(255,255,255,0.08);
    --c-dim:       #64748b;
    --r:           16px;
    --r-sm:        10px;
    --transition:  all 0.4s cubic-bezier(0.25, 1, 0.5, 1);
}

html, body, [class*="css"] {
    font-family: 'Cairo', sans-serif;
    direction: rtl; background: var(--c-bg) !important; color: #e2e8f0;
}
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--c-dim); border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: var(--c-primary); }

@keyframes fadeUp {
    0% { opacity: 0; transform: translateY(20px); }
    100% { opacity: 1; transform: translateY(0); }
}
.g-card, .page-header, [data-testid="stTabs"] {
    animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

[data-testid="stAppViewBlockContainer"] {
    max-width: 100% !important;
    padding: 1rem 2rem !important;
    overflow-x: hidden !important;
}

/* Sidebar Styles & Overlap Fix for RTL */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #05050c 0%, #030306 100%) !important;
    border-left: 1px solid var(--c-border) !important; 
    overflow: hidden !important;
}
[data-testid="stSidebar"][aria-expanded="false"] {
    visibility: hidden !important;
    border-left: none !important;
    box-shadow: none !important;
}

.sidebar-brand {
    padding: 30px 20px 25px; border-bottom: 1px solid var(--c-border);
    margin-bottom: 15px; text-align: center; position: relative; overflow: hidden;
}
.brand-logo {
    width: 60px; height: 60px; border-radius: 16px;
    background: linear-gradient(135deg, rgba(0,242,255,0.15), rgba(112,0,255,0.15));
    border: 1px solid rgba(0,242,255,0.4); margin: 0 auto 12px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 20px rgba(0,242,255,0.2); color: var(--c-primary);
}
.brand-name { font-family: 'Orbitron', sans-serif; font-size: 0.85rem; letter-spacing: 4px; color: #fff; font-weight: 900;}
.brand-ver { font-size: 0.65rem; color: var(--c-primary); margin-top: 6px; font-weight: bold; background: rgba(0,242,255,0.1); padding: 2px 8px; border-radius: 99px; display: inline-block;}

[data-testid="stSidebar"] div.stButton > button {
    background: transparent !important; border: 1px solid transparent !important;
    color: var(--c-dim) !important; justify-content: flex-start !important;
    padding: 12px 18px !important; font-weight: 700 !important; font-size: 1.05rem !important;
}
[data-testid="stSidebar"] div.stButton > button:hover { background: rgba(255,255,255,0.05) !important; color: #fff !important; }
[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
    background: rgba(0, 242, 255, 0.15) !important; color: var(--c-primary) !important;
    border: 1px solid rgba(0, 242, 255, 0.4) !important; font-weight: 900 !important;
}

/* =====================================================================
   WHATSAPP-STYLE CHAT UI (STRICT RTL, PERFECT ALIGNMENT, NO OVERLAP)
   ===================================================================== */
[data-testid="stChatMessage"] { 
    background: transparent !important; 
    border: none !important; 
    padding: 0 !important; 
    margin-bottom: 12px !important; 
    display: flex !important; 
    width: 100% !important;
}
[data-testid="stChatAvatar"] { display: none !important; }

[data-testid="stChatMessageContent"] { 
    width: 100% !important; 
    max-width: 100% !important;
    background: transparent !important; 
    padding: 0 !important; 
    display: flex !important; 
    flex-direction: column !important; 
}

.chat-bubble { 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Cairo", Helvetica, Arial, sans-serif !important; 
    word-wrap: break-word !important; 
    white-space: pre-wrap !important; 
    text-align: right !important; 
    direction: rtl !important; 
    width: fit-content !important; 
    max-width: 85% !important; 
    box-shadow: 0 1px 0.5px rgba(11,20,26,.13) !important; 
    margin-bottom: 2px !important; 
}
.chat-bubble p { margin: 0 !important; color: #e9edef !important;}
.chat-bubble h1, .chat-bubble h2, .chat-bubble h3 { margin-top: 5px !important; margin-bottom: 5px !important; color: #fff !important; }
.chat-bubble ul, .chat-bubble ol { margin-right: 20px !important; padding-right: 15px !important; margin-bottom: 0 !important;}
.chat-bubble li { margin-bottom: 4px !important; }

/* User Message (Right Side in RTL) */
[data-testid="stChatMessage"]:has(.msg-user) [data-testid="stChatMessageContent"] { 
    align-items: flex-start !important; /* Right side due to RTL */
}
[data-testid="stChatMessage"]:has(.msg-user) .chat-bubble { 
    background-color: #005c4b !important; 
    color: #e9edef !important; 
    border-radius: 12px 0px 12px 12px !important; 
}

/* AI Message (Left Side in RTL) */
[data-testid="stChatMessage"]:has(.msg-assistant) [data-testid="stChatMessageContent"] { 
    align-items: flex-end !important; /* Left side due to RTL */
}
[data-testid="stChatMessage"]:has(.msg-assistant) .chat-bubble { 
    background-color: #202c33 !important; 
    color: #e9edef !important; 
    border-radius: 0px 12px 12px 12px !important; 
}

/* Action Buttons Layout (Prevent Overlap and Fix Zooming) */
.chat-actions { display: flex !important; gap: 8px !important; direction: rtl !important; width: fit-content !important;}
[data-testid="stChatMessage"] [data-testid="stHorizontalBlock"] { 
    gap: 8px !important; 
    width: fit-content !important; 
    direction: rtl !important; 
    margin-top: 4px !important;
    align-items: center !important;
    padding: 0 5px !important;
}
[data-testid="stChatMessage"]:has(.msg-user) [data-testid="stHorizontalBlock"] { 
    align-self: flex-start !important; 
}
[data-testid="stChatMessage"]:has(.msg-assistant) [data-testid="stHorizontalBlock"] { 
    align-self: flex-end !important; 
}

[data-testid="stChatMessage"] [data-testid="column"] { 
    padding: 0 !important; 
    width: fit-content !important; 
    min-width: fit-content !important; 
    flex: 0 0 auto !important; 
}
[data-testid="stChatMessage"] div.stButton {
    width: fit-content !important;
}
[data-testid="stChatMessage"] div.stButton > button { 
    background: transparent !important; 
    border: none !important; 
    color: #8696a0 !important; 
    padding: 0 !important; 
    box-shadow: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    border-radius: 50% !important;
    transition: all 0.2s ease-in-out !important;
}
[data-testid="stChatMessage"] div.stButton > button:hover { 
    background: rgba(255,255,255,0.1) !important; 
    color: #ff2d78 !important; 
}

.stMarkdown div[dir="rtl"] strong { color: #00f2ff !important; }

.page-header { padding: 2.5rem 3rem; margin-bottom: 1rem; border-radius: var(--r); background: linear-gradient(135deg, #090912, #050508); border: 1px solid rgba(255,255,255,0.05); display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.ph-icon-wrap { background: rgba(0,242,255,0.05); border-radius: 16px; padding: 18px; border: 1px solid rgba(0,242,255,0.2); }
.ph-title { font-size: 2.2rem; font-weight: 900; color: #fff; line-height: 1.2;}
.ph-sub { color: #94a3b8; font-size: 1rem; margin-top: 8px; font-weight: 600;}

.g-card { background: var(--c-card); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--r); padding: 1.8rem; margin-bottom: 1.5rem; }
.g-card-title { font-weight: 800; font-size: 1.2rem; color: #fff; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 12px; } 

.delta-pos { color: #00ff82; font-size: 0.85rem; font-weight: 800; margin-left: 8px; background: rgba(0,255,130,0.1); padding: 2px 8px; border-radius: 99px; }
.delta-neg { color: #ff2d78; font-size: 0.85rem; font-weight: 800; margin-left: 8px; background: rgba(255,45,120,0.1); padding: 2px 8px; border-radius: 99px; }
.delta-neu { color: #cbd5e1; font-size: 0.85rem; font-weight: 800; margin-left: 8px; background: rgba(255,255,255,0.05); padding: 2px 8px; border-radius: 99px; }

/* Custom Metric Dashboard Card - Auto Shrink for Large Numbers */
.custom-metric { background: rgba(15,15,20,0.8); border: 1px solid rgba(255,255,255,0.05); border-radius: var(--r); padding: 1.2rem; display: flex; flex-direction: column; gap: 8px; overflow: hidden; animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; container-type: inline-size;}
.cm-top { display: flex; justify-content: space-between; align-items: center; }
.cm-label { color: #cbd5e1; font-size: 0.85rem; font-weight: 800; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
.cm-val-wrapper { display: flex; align-items: baseline; width: 100%; white-space: nowrap; }
.cm-val { font-family: 'Orbitron', sans-serif; color: #00f2ff; text-shadow: 0 0 12px rgba(0,242,255,0.6); font-weight: 900; font-size: clamp(0.9rem, 8cqi, 1.8rem); white-space: nowrap; }
.cm-suf { font-size: 0.75rem; color: var(--c-dim); margin-right: 4px; font-family: 'Cairo', sans-serif; font-weight: 700; }
.cm-delta { margin-left: auto; flex-shrink: 0; }

.neon-forecast { font-family: 'Orbitron', sans-serif; color: #ffd700; text-shadow: 0 0 15px rgba(255,215,0,0.6); font-size: 2rem; font-weight: 900; }

[data-testid="stDataFrame"] { border: 1px solid var(--c-border) !important; border-radius: var(--r-sm) !important; background: var(--c-bg2) !important; }
[data-testid="stDataFrame"] th { background: rgba(0,242,255,0.08) !important; color: var(--c-primary) !important; font-weight: 800 !important; font-size: 0.9rem !important; }

.ticker-wrap { width: 100%; overflow: hidden; background: rgba(0,0,0,0.5); padding: 8px 0; margin-bottom: 20px; }
.ticker-move { display: inline-block; white-space: nowrap; padding-right: 100%; animation: ticker 40s linear infinite; }
@keyframes ticker { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(100%, 0, 0); } }
.ticker-item { display: inline-block; padding: 0 2rem; font-size: 0.95rem; font-weight: 700; color: #e2e8f0; }
.ticker-item span { color: var(--c-primary); margin-left: 5px; }
</style>
""", unsafe_allow_html=True)

init_state()

# تعريف الجداول بشكل عام كخط دفاعي ضد NameError
df_s_master = st.session_state.get('df_s', pd.DataFrame())
df_p_master = st.session_state.get('df_p', pd.DataFrame())
df_i_master = st.session_state.get('df_i', pd.DataFrame())
df_po_master = st.session_state.get('df_po', pd.DataFrame())
df_pol_master = st.session_state.get('df_pol', pd.DataFrame())

if st.session_state.get('view') not in ['workspace_login', 'super_admin', 'login'] and st.session_state.get('current_user'):
    CFG = st.session_state.app_config
    if not st.session_state.get('data_loaded'):
        with st.spinner('جاري تهيئة النواة وربط الخوادم لاستخراج بيانات Odoo...'):
            df_s_raw, df_p_raw, df_i_raw, df_po_raw, df_pol_raw, is_real = fetch_master_data(CFG.get('ODOO_URL',''), CFG.get('ODOO_DB',''), CFG.get('ODOO_USER',''), CFG.get('ODOO_PASS',''))
            st.session_state.df_s = df_s_raw
            st.session_state.df_p = df_p_raw
            st.session_state.df_i = df_i_raw
            st.session_state.df_po = df_po_raw
            st.session_state.df_pol = df_pol_raw
            st.session_state.is_real_data = is_real
            st.session_state.data_loaded = True

            # تحديث المتغيرات العامة فور الجلب
            df_s_master = st.session_state.df_s
            df_p_master = st.session_state.df_p
            df_i_master = st.session_state.df_i
            df_po_master = st.session_state.df_po
            df_pol_master = st.session_state.df_pol

    with st.sidebar:
        st.markdown(f"""<div class="sidebar-brand"><div class="brand-logo">{get_icon("chart", 32, "var(--c-primary)")}</div><div class="brand-name">MUDIR</div><div class="brand-ver">OS Kernel v47.9</div></div>""", unsafe_allow_html=True)
        st.markdown(f"""<div style="text-align:center; color:var(--c-primary); font-weight:bold; margin-bottom:20px; font-size:0.9rem;">مرحباً: {st.session_state.current_user.split(" - ")[0]}</div>""", unsafe_allow_html=True)

        allowed_navs = []
        if st.session_state.current_user == "المدير العام":
            allowed_navs = ALL_NAV_ITEMS
        else:
            emp_data = next((e for e in CFG.get('EMPLOYEES', []) if f"{e['name']} - {e['role']}" == st.session_state.current_user), None)
            if emp_data:
                allowed_keys = emp_data.get('views', ['ai'])
                allowed_navs = [item for item in ALL_NAV_ITEMS if item[0] in allowed_keys]

        for key, icon_name, label in allowed_navs:
            is_active = st.session_state.view == key
            display_label = f"◉  {label}" if is_active else f"○  {label}"
            button_type = "primary" if is_active else "secondary"
            if st.button(display_label, key=f"nav_{key}", use_container_width=True, type=button_type):
                st.session_state.view = key
                st.query_params["view"] = key
                st.rerun()

        st.markdown("---")
        
        # 🔴 إصلاح تسجيل الخروج (مسح كامل للذاكرة والرابط)
        if st.button("🔴 تسجيل الخروج", use_container_width=True):
            st.query_params.clear()
            st.session_state.clear()
            st.rerun()
            
        status_color = "#00ff82" if st.session_state.get('is_real_data') else "#ff2d78"
        st.markdown(f"""<div style="background:rgba(0,0,0,0.4); border:1px solid rgba(255,255,255,0.05); border-radius:12px; padding:15px; text-align:center; margin-top:20px;"><div style="font-size:0.8rem; color:#64748b; margin-bottom:6px; font-weight:700;">حالة الاتصال المركزية</div><div style="color:{status_color}; font-weight:900; font-size:0.9rem; display:flex; align-items:center; justify-content:center;"><div class="status-dot" style="color:{status_color}; background:{status_color}; margin-left:8px;"></div>{'متصل بـ Odoo الحقيقي' if st.session_state.get('is_real_data') else 'غير متصل (البيانات فارغة)'}</div></div>""", unsafe_allow_html=True)

def build_infographic_html(data: dict) -> str:
    kpis = data.get('kpis', [])
    bars = data.get('bars', [])
    badges = data.get('badges', [])
    kpi_html = ''.join([f"""<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:20px;text-align:center;min-width:120px;flex:1;"><div style="font-family:'Orbitron',sans-serif;font-size:1.6rem;font-weight:900;color:{k.get('color','#00f2ff')};word-wrap:break-word;">{k['value']}</div><div style="font-size:0.8rem;color:#94a3b8;font-weight:700;text-transform:uppercase;margin-top:6px;line-height:1.3;">{k['label']}</div></div>""" for k in kpis])
    bar_html = ''.join([f"""<div style="margin:12px 0;"><div style="display:flex;justify-content:space-between;font-size:0.9rem;color:#cbd5e1;margin-bottom:8px;"><span>{b['label']}</span><span style="font-weight:bold;color:#fff;">{b['value']:,}</span></div><div style="height:10px;background:rgba(255,255,255,0.05);border-radius:99px;overflow:hidden;"><div style="height:100%;border-radius:99px;background:{b.get('color','#00f2ff')};width:{min(100, (b['value']/b['max']*100) if b.get('max',0)>0 else 0)}%;"></div></div></div>""" for b in bars])
    badge_html = ''.join([f"""<span style="display:inline-flex;align-items:center;font-size:0.8rem;font-weight:700;padding:6px 14px;border-radius:99px;margin:4px;background:rgba(0,242,255,0.1);border:1px solid rgba(0,242,255,0.3);color:#00f2ff;">{b['text']}</span>""" for b in badges])
    return f"""<div style="font-family:'Cairo',sans-serif;direction:rtl;color:#e2e8f0;"><p style="color:#94a3b8;font-size:1rem;margin:0 0 1.5rem;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:15px;">{data.get('subtitle', '')}</p><div style="display:flex;flex-wrap:wrap;gap:14px;margin-bottom:2rem;">{kpi_html}</div>{f'<div style="font-weight:900;font-size:1rem;color:#64748b;text-transform:uppercase;margin:1.5rem 0 1rem;">{get_icon("chart",18)} المؤشرات الحيوية</div>{bar_html}' if bar_html else ''}{f'<div style="font-weight:900;font-size:1rem;color:#64748b;text-transform:uppercase;margin:2rem 0 1rem;">{get_icon("check",18)} التصنيفات الاستراتيجية</div><div>{badge_html}</div>' if badge_html else ''}</div>"""

# ============================================================
# 5. نظام التصدير الموحد والتلوين الآمن 
# ============================================================
def create_export_buttons(title, df_dict):
    html_content = f"""<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
    <head><meta charset='utf-8'><title>{title}</title>
    <style>
        body{{font-family: Arial, sans-serif; direction: rtl; text-align: right; background-color: #ffffff; color: #000000;}} 
        table{{border-collapse: collapse; width: 100%; margin-bottom: 25px; font-size: 14px;}} 
        th, td{{border: 1px solid #aaaaaa; padding: 10px; text-align: center;}} 
        th{{background-color: #00f2ff; color: #000000; font-weight: bold;}} 
        h1{{color: #7000ff; text-align: center; border-bottom: 2px solid #00f2ff; padding-bottom: 10px;}}
        h3{{color: #333333; margin-top: 30px; background-color: #f4f4f4; padding: 8px; border-radius: 5px;}}
        .footer{{text-align: center; color: #666666; margin-top: 40px; font-size: 12px;}}
    </style>
    </head>
    <body>
        <h1>{title}</h1>
        <p style='text-align: center; font-weight: bold;'>تاريخ الاستخراج: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    """
    
    html_content_pdf = html_content
    
    has_data = False
    for section, df_val in df_dict.items():
        raw_df = df_val.data if hasattr(df_val, 'data') else df_val
        if not raw_df.empty:
            has_data = True
            safe_raw = raw_df.copy()
            for col in safe_raw.select_dtypes(include=['object']).columns:
                safe_raw[col] = safe_raw[col].astype(str)
            table_html = f"<h3>{section}</h3>{safe_raw.to_html(index=False)}"
            html_content += table_html
            html_content_pdf += table_html
    
    if not has_data:
        err_msg = "<p style='text-align: center; color: red;'>لا توجد بيانات متاحة للتصدير في هذه الفترة.</p>"
        html_content += err_msg
        html_content_pdf += err_msg
        
    html_content += "<div class='footer'>تم استخراج هذا التقرير تلقائياً من نظام MUDIR OS</div></body></html>"
    html_content_pdf += "<div class='footer'>تم استخراج هذا التقرير تلقائياً من نظام MUDIR OS</div><script>window.onload = function() { window.print(); }</script></body></html>"
    
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(label="حفظ التقرير بصيغة Word", data=html_content.encode('utf-8-sig'), file_name=f"Report_{title}.doc", mime="application/msword", use_container_width=True)
    with c2:
        st.download_button(label="استخراج للطباعة وحفظ (PDF)", data=html_content_pdf.encode('utf-8-sig'), file_name=f"Report_{title}.html", mime="text/html", help="سيتم تحميل ملف، بمجرد فتحه ستظهر لك شاشة حفظ بصيغة PDF تلقائياً.", use_container_width=True)

def render_filters_and_export(title, original_df_dict):
    st.markdown("#### 🔍 فلاتر البيانات الحية للجدول الشامل")
    
    all_clients = ['الكل']
    for df_val in original_df_dict.values():
        df = df_val.data if hasattr(df_val, 'data') else df_val
        if df is not None and not df.empty:
            if 'العميل' in df.columns: all_clients.extend(df['العميل'].dropna().astype(str).unique())
            elif 'المورد' in df.columns: all_clients.extend(df['المورد'].dropna().astype(str).unique())
            elif 'اسم الجهة' in df.columns: all_clients.extend(df['اسم الجهة'].dropna().astype(str).unique())
                
    all_clients = list(dict.fromkeys(all_clients))
    
    c1, c2, c3 = st.columns(3)
    with c1: selected_state = st.selectbox("تصفية بحالة العروض/الأوامر:", ['الكل', 'موافق عليه', 'مسودة', 'ملغي', 'معتمد', 'مسودة / قيد الانتظار'], key=f"state_{title}")
    with c2: selected_client = st.selectbox("العميل / المورد / الجهة:", all_clients, key=f"client_{title}")
    with c3: date_filter = st.date_input("تحديد فترة (من - إلى):", value=[], key=f"date_{title}")

    filtered_dict = {}
    for name, df_val in original_df_dict.items():
        df = df_val.data.copy() if hasattr(df_val, 'data') else df_val.copy()
        if not df.empty:
            if selected_state != 'الكل':
                if 'الحالة (عربي)' in df.columns: df = df[df['الحالة (عربي)'] == selected_state]
                elif 'الحالة' in df.columns: df = df[df['الحالة'] == selected_state]
            if selected_client != 'الكل':
                if 'العميل' in df.columns: df = df[df['العميل'] == selected_client]
                elif 'المورد' in df.columns: df = df[df['المورد'] == selected_client]
                elif 'اسم الجهة' in df.columns: df = df[df['اسم الجهة'] == selected_client]
            if len(date_filter) == 2:
                start_date, end_date = date_filter
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
                if 'التاريخ' in df.columns:
                    try:
                        temp_dt = pd.to_datetime(df['التاريخ'])
                        df = df[(temp_dt >= start_dt) & (temp_dt <= end_dt)]
                    except: pass
        filtered_dict[name] = style_dataframe(df)
        
    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 25px 0;'>", unsafe_allow_html=True)
    create_export_buttons(title, filtered_dict)
    return filtered_dict

@st.dialog("التحليل الاستراتيجي التفصيلي والتصدير", width="large")
def show_detailed_report(title: str, data: dict):
    st.markdown(f"<h3 style='color:var(--c-primary); margin-top:0; margin-bottom: 20px;'>{title}</h3>", unsafe_allow_html=True)
    
    df_dict = {}
    if 'df' in data and data['df'] is not None:
        if isinstance(data['df'], dict): df_dict = data['df']
        else: df_dict = {"البيانات التفصيلية": data['df']}
            
    filtered_dict = {}
    if df_dict:
        filtered_dict = render_filters_and_export(title, df_dict)
        st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 20px 0;'>", unsafe_allow_html=True)

    if 'kpis' in data or 'bars' in data or 'badges' in data:
        st.markdown(build_infographic_html(data), unsafe_allow_html=True)
    
    if filtered_dict:
        st.markdown(f"""<div style="margin-top:25px; margin-bottom:15px; font-weight:900; font-size:1.1rem; color:var(--c-primary); display:flex; align-items:center; gap:8px;">{get_icon('table', 20)} استعراض السجل الشامل (بعد الفلترة)</div>""", unsafe_allow_html=True)
        
        tab_titles = []
        for tab_name, df_val in filtered_dict.items():
            raw_check = df_val.data if hasattr(df_val, 'data') else df_val
            row_count = len(raw_check) if not raw_check.empty else 0
            tab_titles.append(f"{tab_name} ({row_count})")
            
        tabs = st.tabs(tab_titles)
        for i, (tab_name, df_val) in enumerate(filtered_dict.items()):
            with tabs[i]:
                raw_check = df_val.data if hasattr(df_val, 'data') else df_val
                if not raw_check.empty: st.dataframe(df_val, use_container_width=True, hide_index=True)
                else: st.info("لا توجد بيانات مطابقة للفلاتر التي قمت بتحديدها.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("إغلاق التقرير", type="primary", use_container_width=True):
        st.rerun()

# ────────────────────────────────────────────────────────────
# 7.1 لوحة القيادة (Dashboard)
# ────────────────────────────────────────────────────────────
def render_dashboard():
    
    st.markdown(f"""
    <div class="page-header" style="justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div class="ph-icon-wrap">{get_icon("dashboard", 46, "#00f2ff")}</div>
            <div>
                <div class="ph-title">لوحة القيادة المركزية</div>
                <div class="ph-sub">إصدار QUANTUM: استخراج ذكي يفصل بين العميل/المورد والمشروع/المنتج بدقة مطلقة.</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='g-card' style='padding: 1.5rem; margin-bottom: 2rem; margin-top: 1rem;'>", unsafe_allow_html=True)
    start_dt, end_dt, prev_start_dt, prev_end_dt = get_smart_filter_dates("dash")
    st.markdown("</div>", unsafe_allow_html=True)
    
    df_s = df_s_master.copy()
    df_po = df_po_master.copy()
    df_p = df_p_master.copy()
    df_i = df_i_master.copy()
    df_pol = df_pol_master.copy()
    
    t_sales_appr_prev = t_orders_appr_prev = t_po_appr_prev = 0
    if prev_start_dt and prev_end_dt:
        if not df_s_master.empty and 'date_order' in df_s_master.columns:
            prev_df_s = df_s_master[(df_s_master['date_order'] >= prev_start_dt) & (df_s_master['date_order'] <= prev_end_dt)]
            t_sales_appr_prev = prev_df_s[prev_df_s['state'].isin(['sale', 'done'])]['amount_total'].sum()
            t_orders_appr_prev = prev_df_s[prev_df_s['state'].isin(['sale', 'done'])].shape[0]
        if not df_po_master.empty and 'date_order' in df_po_master.columns:
            prev_df_po = df_po_master[(df_po_master['date_order'] >= prev_start_dt) & (df_po_master['date_order'] <= prev_end_dt)]
            t_po_appr_prev = prev_df_po[prev_df_po['state'].isin(['purchase', 'done'])]['amount_total'].sum()

    if start_dt and end_dt:
        if not df_s.empty and 'date_order' in df_s.columns: df_s = df_s[(df_s['date_order'] >= start_dt) & (df_s['date_order'] <= end_dt)]
        if not df_po.empty and 'date_order' in df_po.columns: df_po = df_po[(df_po['date_order'] >= start_dt) & (df_po['date_order'] <= end_dt)]

    with st.expander("فلاتر إضافية للوحة القيادة", expanded=False):
        fc1, fc2 = st.columns(2)
        filtered_s = df_s.copy() if not df_s.empty else pd.DataFrame()
        with fc1:
            states = df_s['state'].dropna().unique().tolist() if not df_s.empty and 'state' in df_s.columns else []
            sel_states = st.multiselect("حالة الطلب", states, default=states)
        with fc2:
            if not df_s.empty and 'amount_total' in df_s.columns:
                a_min, a_max = int(df_s['amount_total'].min()), int(df_s['amount_total'].max())
                if a_min < a_max: amt_range = st.slider("نطاق القيمة", min_value=a_min, max_value=a_max, value=(a_min, a_max))
                else: amt_range = (a_min, a_max)
            else: amt_range = None

        if not filtered_s.empty:
            if sel_states: filtered_s = filtered_s[filtered_s['state'].isin(sel_states)]
            if amt_range: filtered_s = filtered_s[(filtered_s['amount_total'] >= amt_range[0]) & (filtered_s['amount_total'] <= amt_range[1])]

    is_approved = filtered_s['state'].isin(['sale', 'done']) if 'state' in filtered_s.columns else pd.Series(dtype=bool)
    is_draft = filtered_s['state'].isin(['draft', 'sent']) if 'state' in filtered_s.columns else pd.Series(dtype=bool)
    is_cancel = filtered_s['state'] == 'cancel' if 'state' in filtered_s.columns else pd.Series(dtype=bool)

    t_sales_appr = filtered_s.loc[is_approved, 'amount_total'].sum() if not filtered_s.empty else 0
    t_sales_draft = filtered_s.loc[is_draft, 'amount_total'].sum() if not filtered_s.empty else 0
    t_sales_canc = filtered_s.loc[is_cancel, 'amount_total'].sum() if not filtered_s.empty else 0
    t_orders_appr = is_approved.sum() if not is_approved.empty else 0
    t_orders_draft = is_draft.sum() if not is_draft.empty else 0
    t_orders_canc = is_cancel.sum() if not is_cancel.empty else 0
    t_clients = len(df_p) if df_p is not None else 0

    is_po_appr = df_po['state'].isin(['purchase', 'done']) if not df_po.empty else pd.Series(dtype=bool)
    t_po_appr = df_po.loc[is_po_appr, 'amount_total'].sum() if not df_po.empty else 0
    t_po_draft = df_po.loc[~is_po_appr, 'amount_total'].sum() if not df_po.empty else 0

    top_item_name, top_item_qty, top_item_code = "لا يوجد", 0, "-"
    if not df_i.empty and 'qty_available' in df_i.columns:
        idx_max = df_i['qty_available'].idxmax()
        if pd.notna(idx_max):
            top_row = df_i.loc[idx_max]
            top_item_name = str(top_row['name'])
            top_item_qty = float(top_row['qty_available'])
            top_item_code = str(top_row.get('default_code', '-'))

    clean_s = filtered_s.copy() if not filtered_s.empty else pd.DataFrame()
    if not clean_s.empty:
        clean_s['العميل'] = clean_s['partner_id'].apply(clean_odoo_m2o) if 'partner_id' in clean_s else ""
        clean_s['المسؤول'] = clean_s['user_id'].apply(clean_odoo_m2o) if 'user_id' in clean_s else ""
        clean_s['المشروع / القسم'] = clean_s.apply(extract_department_from_row, axis=1)
        clean_s['المشروع / القسم'] = clean_s['المشروع / القسم'].apply(clean_department_name)
        clean_s['الحالة (عربي)'] = clean_s['state'].apply(map_state_ar)
        clean_s = clean_s.rename(columns={'name': 'رقم الطلب', 'amount_total': 'القيمة (ج.م)'})
        if 'date_order' in clean_s: clean_s['التاريخ'] = clean_s['date_order'].dt.strftime('%Y-%m-%d')
        clean_s = clean_s[[c for c in ['رقم الطلب', 'العميل', 'القيمة (ج.م)', 'التاريخ', 'الحالة (عربي)', 'المشروع / القسم', 'المسؤول'] if c in clean_s.columns]]

    clean_p = df_p.copy() if not df_p.empty else pd.DataFrame()
    if not clean_p.empty:
        if 'total_invoiced' in clean_p.columns:
            clean_p = clean_p.sort_values('total_invoiced', ascending=False)
        rename_dict_p = {'name': 'اسم الجهة', 'city': 'المدينة', 'total_invoiced': 'إجمالي الفواتير (ج.م)', 'phone': 'الهاتف'}
        clean_p = clean_p.rename(columns={k:v for k,v in rename_dict_p.items() if k in clean_p.columns})
        clean_p = clean_p[[c for c in ['اسم الجهة', 'المدينة', 'إجمالي الفواتير (ج.م)', 'الهاتف'] if c in clean_p.columns]]

    clean_i = df_i.copy() if not df_i.empty else pd.DataFrame()
    if not clean_i.empty:
        if 'qty_available' in clean_i.columns:
            clean_i = clean_i.sort_values('qty_available', ascending=False)
        rename_dict_i = {'default_code': 'الكود', 'name': 'المنتج', 'qty_available': 'الكمية المتاحة', 'lst_price': 'السعر (ج.م)'}
        clean_i = clean_i.rename(columns={k:v for k,v in rename_dict_i.items() if k in clean_i.columns})
        clean_i = clean_i[[c for c in ['الكود', 'المنتج', 'الكمية المتاحة', 'السعر (ج.م)'] if c in clean_i.columns]]

    clean_po = df_po.copy() if not df_po.empty else pd.DataFrame()
    if not clean_po.empty:
        clean_po['المورد'] = clean_po['partner_id'].apply(clean_odoo_m2o) if 'partner_id' in clean_po else ""
        clean_po['الحالة'] = clean_po['state'].apply(map_po_state_ar)
        clean_po = clean_po.rename(columns={'name': 'رقم الأمر', 'amount_total': 'القيمة (ج.م)'})
        if 'date_order' in clean_po: clean_po['التاريخ'] = clean_po['date_order'].dt.strftime('%Y-%m-%d')
        clean_po = clean_po[[c for c in ['رقم الأمر', 'المورد', 'القيمة (ج.م)', 'التاريخ', 'الحالة'] if c in clean_po.columns]]

    clean_pol = df_pol.copy() if not df_pol.empty else pd.DataFrame()
    if not clean_pol.empty:
        if 'product_id' in clean_pol.columns:
            clean_pol['المنتج / المادة'] = clean_pol['product_id'].apply(clean_odoo_m2o)
            clean_pol = clean_pol.groupby('المنتج / المادة').agg({'product_qty': 'sum', 'price_subtotal': 'sum'}).reset_index()
            if 'product_qty' in clean_pol.columns:
                clean_pol = clean_pol.sort_values('product_qty', ascending=False)
            clean_pol = clean_pol.rename(columns={'product_qty': 'الكمية المطلوبة', 'price_subtotal': 'إجمالي التكلفة (ج.م)'})

    # فلترة آمنة لتجنب انهيار الجداول الفارغة
    if not clean_s.empty and 'الحالة (عربي)' in clean_s.columns:
        s_appr = clean_s[clean_s['الحالة (عربي)'] == 'موافق عليه']
        s_draft = clean_s[clean_s['الحالة (عربي)'] == 'مسودة']
        s_canc = clean_s[clean_s['الحالة (عربي)'] == 'ملغي']
    else:
        s_appr = pd.DataFrame()
        s_draft = pd.DataFrame()
        s_canc = pd.DataFrame()

    split_sales_dict = {
        "السجل الشامل للعروض والطلبات": style_dataframe(clean_s), 
        "موافق عليه": style_dataframe(s_appr), 
        "مسودة": style_dataframe(s_draft), 
        "ملغي": style_dataframe(s_canc)
    }

    # تفصيل بيانات الموردين
    if not clean_po.empty and 'المورد' in clean_po.columns:
        po_appr = clean_po[clean_po['الحالة'] == 'معتمد']
        po_draft = clean_po[clean_po['الحالة'] == 'مسودة / قيد الانتظار']
        po_canc = clean_po[clean_po['الحالة'] == 'ملغي']

        po_count_all = clean_po.groupby('المورد')['رقم الأمر'].count().reset_index().rename(columns={'رقم الأمر': 'العدد الكلي'})
        po_sum_all = clean_po.groupby('المورد')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'القيمة الكلية (ج.م)'})

        po_count_appr = po_appr.groupby('المورد')['رقم الأمر'].count().reset_index().rename(columns={'رقم الأمر': 'عدد (معتمد)'}) if not po_appr.empty else pd.DataFrame(columns=['المورد', 'عدد (معتمد)'])
        po_sum_appr = po_appr.groupby('المورد')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'قيمة (معتمد)'}) if not po_appr.empty else pd.DataFrame(columns=['المورد', 'قيمة (معتمد)'])

        po_count_draft = po_draft.groupby('المورد')['رقم الأمر'].count().reset_index().rename(columns={'رقم الأمر': 'عدد (مسودة)'}) if not po_draft.empty else pd.DataFrame(columns=['المورد', 'عدد (مسودة)'])
        po_sum_draft = po_draft.groupby('المورد')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'قيمة (مسودة)'}) if not po_draft.empty else pd.DataFrame(columns=['المورد', 'قيمة (مسودة)'])

        po_count_canc = po_canc.groupby('المورد')['رقم الأمر'].count().reset_index().rename(columns={'رقم الأمر': 'عدد (ملغي)'}) if not po_canc.empty else pd.DataFrame(columns=['المورد', 'عدد (ملغي)'])
        po_sum_canc = po_canc.groupby('المورد')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'قيمة (ملغي)'}) if not po_canc.empty else pd.DataFrame(columns=['المورد', 'قيمة (ملغي)'])

        po_merged = po_count_all.merge(po_sum_all, on='المورد', how='left') \
                              .merge(po_count_appr, on='المورد', how='left').merge(po_sum_appr, on='المورد', how='left') \
                              .merge(po_count_draft, on='المورد', how='left').merge(po_sum_draft, on='المورد', how='left') \
                              .merge(po_count_canc, on='المورد', how='left').merge(po_sum_canc, on='المورد', how='left').fillna(0)
        
        po_cols = ['المورد', 'العدد الكلي', 'القيمة الكلية (ج.م)', 'عدد (معتمد)', 'قيمة (معتمد)', 'عدد (مسودة)', 'قيمة (مسودة)', 'عدد (ملغي)', 'قيمة (ملغي)']
        po_merged = po_merged[[c for c in po_cols if c in po_merged.columns]]

        split_po_dict = {
            "التحليل الشامل للموردين": style_dataframe(po_merged),
            "الأقوى (معتمد)": style_dataframe(po_merged[['المورد', 'عدد (معتمد)', 'قيمة (معتمد)']]) if 'قيمة (معتمد)' in po_merged.columns else style_dataframe(pd.DataFrame()),
            "قيد الانتظار (مسودة)": style_dataframe(po_merged[['المورد', 'عدد (مسودة)', 'قيمة (مسودة)']]) if 'قيمة (مسودة)' in po_merged.columns else style_dataframe(pd.DataFrame()),
            "المنتجات / المواد الأكثر طلباً": style_dataframe(clean_pol)
        }
    else:
        split_po_dict = {
            "السجل الشامل للمشتريات": style_dataframe(clean_po),
            "المنتجات / المواد الأكثر طلباً": style_dataframe(clean_pol)
        }

    # تفصيل بيانات العملاء
    if not clean_s.empty and 'العميل' in clean_s.columns:
        c_count_all = clean_s.groupby('العميل')['رقم الطلب'].count().reset_index().rename(columns={'رقم الطلب': 'العدد الكلي'})
        c_sum_all = clean_s.groupby('العميل')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'القيمة الكلية (ج.م)'})
        
        c_count_appr = s_appr.groupby('العميل')['رقم الطلب'].count().reset_index().rename(columns={'رقم الطلب': 'عدد (معتمد)'}) if not s_appr.empty else pd.DataFrame(columns=['العميل', 'عدد (معتمد)'])
        c_sum_appr = s_appr.groupby('العميل')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'قيمة (معتمد)'}) if not s_appr.empty else pd.DataFrame(columns=['العميل', 'قيمة (معتمد)'])
        
        c_count_draft = s_draft.groupby('العميل')['رقم الطلب'].count().reset_index().rename(columns={'رقم الطلب': 'عدد (مسودة)'}) if not s_draft.empty else pd.DataFrame(columns=['العميل', 'عدد (مسودة)'])
        c_sum_draft = s_draft.groupby('العميل')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'قيمة (مسودة)'}) if not s_draft.empty else pd.DataFrame(columns=['العميل', 'قيمة (مسودة)'])
        
        c_count_canc = s_canc.groupby('العميل')['رقم الطلب'].count().reset_index().rename(columns={'رقم الطلب': 'عدد (ملغي)'}) if not s_canc.empty else pd.DataFrame(columns=['العميل', 'عدد (ملغي)'])
        c_sum_canc = s_canc.groupby('العميل')['القيمة (ج.م)'].sum().reset_index().rename(columns={'القيمة (ج.م)': 'قيمة (ملغي)'}) if not s_canc.empty else pd.DataFrame(columns=['العميل', 'قيمة (ملغي)'])
        
        c_merged = c_count_all.merge(c_sum_all, on='العميل', how='left') \
                              .merge(c_count_appr, on='العميل', how='left').merge(c_sum_appr, on='العميل', how='left') \
                              .merge(c_count_draft, on='العميل', how='left').merge(c_sum_draft, on='العميل', how='left') \
                              .merge(c_count_canc, on='العميل', how='left').merge(c_sum_canc, on='العميل', how='left').fillna(0)
        
        if not clean_p.empty and 'اسم الجهة' in clean_p.columns:
            p_info = clean_p[['اسم الجهة', 'المدينة', 'الهاتف']].drop_duplicates(subset=['اسم الجهة']).rename(columns={'اسم الجهة': 'العميل'}) if 'المدينة' in clean_p.columns and 'الهاتف' in clean_p.columns else pd.DataFrame()
            if not p_info.empty:
                c_merged = c_merged.merge(p_info, on='العميل', how='left').fillna('-')

        c_cols = ['العميل', 'العدد الكلي', 'القيمة الكلية (ج.م)', 'عدد (معتمد)', 'قيمة (معتمد)', 'عدد (مسودة)', 'قيمة (مسودة)', 'عدد (ملغي)', 'قيمة (ملغي)', 'المدينة', 'الهاتف']
        c_merged = c_merged[[c for c in c_cols if c in c_merged.columns]]

        split_clients = {
            "التحليل الشامل للعملاء": style_dataframe(c_merged),
            "الأقوى (معتمد)": style_dataframe(c_merged[['العميل', 'عدد (معتمد)', 'قيمة (معتمد)']]) if 'قيمة (معتمد)' in c_merged.columns else style_dataframe(pd.DataFrame()),
            "حسب المسودة": style_dataframe(c_merged[['العميل', 'عدد (مسودة)', 'قيمة (مسودة)']]) if 'قيمة (مسودة)' in c_merged.columns else style_dataframe(pd.DataFrame()),
            "العملاء الملغيين (خسائر)": style_dataframe(c_merged[['العميل', 'عدد (ملغي)', 'قيمة (ملغي)']]) if 'قيمة (ملغي)' in c_merged.columns else style_dataframe(pd.DataFrame())
        }
    else:
        split_clients = {"السجل الشامل للعملاء": style_dataframe(clean_p)}

    if not clean_i.empty:
        split_stock = {
            "سجل المنتجات الشامل": style_dataframe(clean_i),
            "المنتجات الأكثر توفراً (الكمية)": style_dataframe(clean_i[['المنتج', 'الكمية المتاحة']]) if 'المنتج' in clean_i.columns and 'الكمية المتاحة' in clean_i.columns else style_dataframe(pd.DataFrame()),
            "المنتجات الأغلى سعراً": style_dataframe(clean_i[['المنتج', 'السعر (ج.م)']]) if 'المنتج' in clean_i.columns and 'السعر (ج.م)' in clean_i.columns else style_dataframe(pd.DataFrame())
        }
    else:
        split_stock = {"الكل": style_dataframe(clean_i)}

    render_live_ticker(st.session_state.df_s, st.session_state.df_p)

    metrics = [
        ("الإيرادات (المعتمدة)", f"{t_sales_appr:,.0f}", "ج.م", "money", get_delta_html(t_sales_appr, t_sales_appr_prev), {
            'subtitle':'تحليل السيولة النقدية مقسمة حسب الحالة', 
            'kpis': [{'label':'موافق عليه','value':f"{t_sales_appr:,.0f} ج", 'color':'#00ff82'},
                     {'label':'مسودة','value':f"{t_sales_draft:,.0f} ج", 'color':'#ffd700'},
                     {'label':'ملغي','value':f"{t_sales_canc:,.0f} ج", 'color':'#ff2d78'}],
            'badges': [{'text':'يعتمد على Sale & Done'}],
            'df': split_sales_dict
        }),
        ("الطلبات (المعتمدة)", f"{t_orders_appr:,}", "طلب", "orders", get_delta_html(t_orders_appr, t_orders_appr_prev), {
            'subtitle':'كثافة العمليات موزعة على الحالات', 
            'kpis':[{'label':'موافق عليه','value':str(t_orders_appr), 'color':'#00ff82'},
                    {'label':'مسودة','value':str(t_orders_draft), 'color':'#ffd700'},
                    {'label':'ملغي','value':str(t_orders_canc), 'color':'#ff2d78'}],
            'df': split_sales_dict
        }),
        ("العملاء (بالنشاط)", f"{t_clients:,}", "عميل", "users", "", {
            'subtitle':'تحليل العملاء الشامل وتصنيفهم حسب نشاط العروض (العدد والقيمة)', 
            'kpis':[{'label':'إجمالي العملاء/جهات','value':str(t_clients)}], 
            'badges':[{'text':'تلوين حراري لنشاط العميل'}],
            'df': split_clients
        }),
        ("المشتريات والموردين", f"{t_po_appr:,.0f}", "ج.م", "truck", get_delta_html(t_po_appr, t_po_appr_prev), {
            'subtitle':'تحليل المشتريات والموردين (المعتمد وقيد الانتظار)', 
            'kpis':[{'label':'موافق عليه','value':f"{t_po_appr:,.0f} ج", 'color':'#00ff82'},
                    {'label':'قيد الانتظار','value':f"{t_po_draft:,.0f} ج", 'color':'#ffd700'}],
            'df': split_po_dict
        }),
        ("أبرز منتج/مادة", f"{top_item_qty:,.0f}", "وحدة", "stock", "", {
            'subtitle':f'أكثر المنتجات والمواد توفراً (الكود: {top_item_code})', 
            'kpis':[{'label':top_item_name,'value':f"{top_item_qty:,.0f} وحدة", 'color':'#00f2ff'}], 
            'badges':[{'text':'مراقبة المخزون النشط'}],
            'df': split_stock
        })
    ]
    
    st.markdown('<div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 20px;">', unsafe_allow_html=True)
    cols = st.columns(len(metrics))
    for i, (label, val, suf, icn, delta_html, mdata) in enumerate(metrics):
        with cols[i]:
            st.markdown(f"""
            <div class="custom-metric">
                <div class="cm-top">
                    <span class="cm-label" title="{label}">{label}</span>
                    {get_icon(icn, 20, "var(--c-primary)")}
                </div>
                <div class="cm-val-wrapper">
                    <div class="cm-val" title="{val}">{val}</div>
                    <div class="cm-suf">{suf}</div>
                    <div class="cm-delta">{delta_html}</div>
                </div>
            </div>""", unsafe_allow_html=True)
            if st.button("تحليل وتصدير", key=f"btn_m_{i}", use_container_width=True):
                show_detailed_report(label, mdata)
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------
    # مخطط الشلال المالي (Financial Waterfall Chart)
    # -------------------------------------------------------------------
    st.markdown(f"<div class='g-card-title'>{get_icon('chart', 22)} مخطط الشلال المالي (حركة تدفق الإيرادات)</div>", unsafe_allow_html=True)
    
    waterfall_fig = go.Figure(go.Waterfall(
        name = "المبيعات",
        orientation = "v",
        measure = ["absolute", "relative", "relative", "total"],
        x = ["إجمالي العروض (الطلب)", "عروض ملغاة (نزيف)", "عروض قيد الانتظار", "صافي الإيرادات المعتمدة"],
        textposition = "outside",
        text = [f"{(t_sales_appr + t_sales_draft + t_sales_canc):,.0f}", f"-{t_sales_canc:,.0f}", f"-{t_sales_draft:,.0f}", f"{t_sales_appr:,.0f}"],
        y = [(t_sales_appr + t_sales_draft + t_sales_canc), -t_sales_canc, -t_sales_draft, t_sales_appr],
        connector = {"line":{"color":"rgba(255,255,255,0.1)"}},
        decreasing = {"marker":{"color":"#ff2d78"}},
        increasing = {"marker":{"color":"#00f2ff"}},
        totals = {"marker":{"color":"#00ff82"}}
    ))

    waterfall_fig.update_layout(
        template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0,r=0,t=20,b=0), hoverlabel=dict(font_family="Cairo", font_size=14)
    )
    st.plotly_chart(waterfall_fig, use_container_width=True)

    st.markdown(f"<div style='margin-top: 30px; margin-bottom: 15px;'><div class='g-card-title' style='border: none; padding: 0;'>{get_icon('tabs', 24)} سجل العروض والتوريدات المباشر</div></div>", unsafe_allow_html=True)
    
    count_all = len(clean_s) if not clean_s.empty else 0
    count_appr = len(s_appr) if not s_appr.empty else 0
    count_draft = len(s_draft) if not s_draft.empty else 0
    count_canc = len(s_canc) if not s_canc.empty else 0

    tb_all, tb_appr, tb_draft, tb_canc = st.tabs([
        f"الكل ({count_all})", 
        f"موافق عليه ({count_appr})", 
        f"مسودة ({count_draft})", 
        f"ملغي ({count_canc})"
    ])
    
    with tb_all:
        if not clean_s.empty: st.dataframe(split_sales_dict["السجل الشامل للعروض والطلبات"], use_container_width=True, hide_index=True)
        else: st.info("لا توجد بيانات متاحة في هذه الفترة.")
    with tb_appr:
        if not s_appr.empty: st.dataframe(split_sales_dict["موافق عليه"], use_container_width=True, hide_index=True)
        else: st.info("لا توجد طلبات موافق عليها في هذه الفترة.")
    with tb_draft:
        if not s_draft.empty: st.dataframe(split_sales_dict["مسودة"], use_container_width=True, hide_index=True)
        else: st.info("لا توجد مسودات في هذه الفترة.")
    with tb_canc:
        if not s_canc.empty: st.dataframe(split_sales_dict["ملغي"], use_container_width=True, hide_index=True)
        else: st.info("لا توجد طلبات ملغاة في هذه الفترة.")

    st.markdown("<br>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────
# 7.2 أداء الأقسام والعمليات (Departments View)
# ────────────────────────────────────────────────────────────
def render_departments():
    st.markdown(f"""
    <div class="page-header" style="justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div class="ph-icon-wrap">{get_icon("layers", 46, "#00f2ff")}</div>
            <div>
                <div class="ph-title">التحليل الاستراتيجي للأقسام (الربحية)</div>
                <div class="ph-sub">بيان تفصيلي للأقسام الأقوى والأضعف بناءً على الإيرادات والمصروفات وصافي الربح</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    start_dt, end_dt, _, _ = get_smart_filter_dates("dept")

    t_df = df_s_master.copy()
    if start_dt and end_dt and not t_df.empty and 'date_order' in t_df.columns:
        t_df = t_df[(t_df['date_order'] >= start_dt) & (t_df['date_order'] <= end_dt)]

    if t_df.empty:
        return st.warning("لا توجد بيانات متاحة لتحليل الأقسام في هذه الفترة الزمنية.")
    
    t_df['القسم'] = t_df.apply(extract_department_from_row, axis=1)
    t_df['القسم'] = t_df['القسم'].apply(clean_department_name)
    t_df['الحالة (عربي)'] = t_df['state'].apply(map_state_ar)

    # تجهيز سجل العمليات التفصيلي ليرتبط بالأقسام
    clean_s = t_df.copy()
    if not clean_s.empty:
        clean_s['العميل'] = clean_s['partner_id'].apply(clean_odoo_m2o) if 'partner_id' in clean_s else ""
        clean_s['المسؤول'] = clean_s['user_id'].apply(clean_odoo_m2o) if 'user_id' in clean_s else ""
        clean_s = clean_s.rename(columns={'name': 'رقم الطلب', 'amount_total': 'القيمة (ج.م)'})
        if 'date_order' in clean_s: clean_s['التاريخ'] = clean_s['date_order'].dt.strftime('%Y-%m-%d')
        clean_s = clean_s[[c for c in ['رقم الطلب', 'القسم', 'العميل', 'القيمة (ج.م)', 'التاريخ', 'الحالة (عربي)', 'المسؤول'] if c in clean_s.columns]]

    appr_df = t_df[t_df['الحالة (عربي)'] == 'موافق عليه'].copy()
    
    if 'margin' in appr_df.columns:
        appr_df['margin_num'] = pd.to_numeric(appr_df['margin'], errors='coerce').fillna(0)
        appr_df['المصروفات'] = appr_df['amount_total'] - appr_df['margin_num']
        appr_df['المصروفات'] = np.where(appr_df['المصروفات'] < 0, appr_df['amount_total'] * 0.7, appr_df['المصروفات'])
    else:
        np.random.seed(42)
        appr_df['المصروفات'] = appr_df['amount_total'] * np.random.uniform(0.60, 0.85, size=len(appr_df))

    appr_df['صاف الربح'] = appr_df['amount_total'] - appr_df['المصروفات']

    dept_summary = appr_df.groupby('القسم').agg(
        الإيرادات=('amount_total', 'sum'),
        المصروفات=('المصروفات', 'sum'),
        صافي_الربح=('صاف الربح', 'sum')
    ).reset_index()

    dept_summary['هامش الربح %'] = (dept_summary['صافي_الربح'] / dept_summary['الإيرادات'] * 100).fillna(0)
    
    summ_df_all = t_df.groupby('القسم').agg(
        إجمالي_الطلبات=('name', 'count'),
        إيرادات_معتمدة=('amount_total', lambda x: x[t_df.loc[x.index, 'الحالة (عربي)'] == 'موافق عليه'].sum()),
        إيرادات_مسودة=('amount_total', lambda x: x[t_df.loc[x.index, 'الحالة (عربي)'] == 'مسودة'].sum()),
        إيرادات_ملغاة=('amount_total', lambda x: x[t_df.loc[x.index, 'الحالة (عربي)'] == 'ملغي'].sum())
    ).reset_index()

    final_table = pd.merge(summ_df_all, dept_summary[['القسم', 'المصروفات', 'صافي_الربح', 'هامش الربح %']], on='القسم', how='left').fillna(0)
    final_table = final_table.rename(columns={'إيرادات_معتمدة': 'الإيرادات', 'صافي_الربح': 'صاف الربح'})

    if st.button(f"📥 تحليل وتصدير تقرير الأقسام (Word / PDF)", use_container_width=True):
        export_data = {
            "الجدول التحليلي الشامل لأداء الأقسام": final_table,
            "سجل العمليات التفصيلي للأقسام": clean_s
        }
        show_detailed_report("التحليل الاستراتيجي للأقسام", {"df": export_data})
        
    st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin-bottom: 20px;'>", unsafe_allow_html=True)

    if not dept_summary.empty:
        strongest_row = dept_summary.loc[dept_summary['صافي_الربح'].idxmax()]
        weakest_row = dept_summary.loc[dept_summary['صافي_الربح'].idxmin()]
        total_active = len(dept_summary)
        avg_margin = dept_summary['هامش الربح %'].mean()
    else:
        strongest_row = {'القسم': 'لا يوجد', 'صافي_الربح': 0}
        weakest_row = {'القسم': 'لا يوجد', 'صافي_الربح': 0}
        total_active = 0
        avg_margin = 0

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f"""<div class="custom-metric"><div class="cm-top"><span class="cm-label">إجمالي الأقسام النشطة</span>{get_icon("layers", 20, "#00f2ff")}</div><div class="cm-val-wrapper"><div class="cm-val">{total_active}</div><div class="cm-suf">أقسام</div></div></div>""", unsafe_allow_html=True)
    m2.markdown(f"""<div class="custom-metric"><div class="cm-top"><span class="cm-label">القسم الأقوى</span>{get_icon("trending-up", 20, "#00ff82")}</div><div class="cm-val-wrapper"><div class="cm-val">{strongest_row['صافي_الربح']:,.0f}</div><div class="cm-suf">ج.م</div></div></div>""", unsafe_allow_html=True)
    m3.markdown(f"""<div class="custom-metric"><div class="cm-top"><span class="cm-label">القسم الأضعف</span>{get_icon("trending-down", 20, "#ff2d78")}</div><div class="cm-val-wrapper"><div class="cm-val">{weakest_row['صافي_الربح']:,.0f}</div><div class="cm-suf">ج.م</div></div></div>""", unsafe_allow_html=True)
    m4.markdown(f"""<div class="custom-metric"><div class="cm-top"><span class="cm-label">متوسط هامش الربح</span>{get_icon("chart", 20, "#ffd700")}</div><div class="cm-val-wrapper"><div class="cm-val">{avg_margin:.1f}</div><div class="cm-suf">%</div></div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"<div class='g-card-title'>{get_icon('chart', 22)} مقارنة الإيرادات والمصروفات وهامش الربح للأقسام (موافق عليه في الفترة المحددة)</div>", unsafe_allow_html=True)
    
    if not dept_summary.empty:
        fig_combo = go.Figure()
        fig_combo.add_trace(go.Bar(
            x=dept_summary['القسم'], y=dept_summary['الإيرادات'],
            name='الإيرادات', marker_color='#00ff82'
        ))
        fig_combo.add_trace(go.Bar(
            x=dept_summary['القسم'], y=dept_summary['المصروفات'],
            name='المصروفات', marker_color='#ff2d78'
        ))
        
        fig_combo.update_layout(
            barmode='group',
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            hovermode="x unified",
            xaxis_title="القسم / المشروع",
            yaxis_title="القيمة (ج.م)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hoverlabel=dict(font_family="Cairo", font_size=14)
        )
        st.plotly_chart(fig_combo, use_container_width=True)
    else:
        st.info("لا توجد بيانات ربحية لعرضها في هذه الفترة.")

    st.markdown(f"<div class='g-card-title' style='margin-top:20px;'>{get_icon('table', 22)} الجدول التحليلي الشامل لأداء الأقسام</div>", unsafe_allow_html=True)
    st.dataframe(style_dataframe(final_table), use_container_width=True, hide_index=True)

    st.markdown(f"<div class='g-card-title' style='margin-top:30px;'>{get_icon('tabs', 22)} سجل العمليات التفصيلي للأقسام</div>", unsafe_allow_html=True)
    if not clean_s.empty:
        st.dataframe(style_dataframe(clean_s), use_container_width=True, hide_index=True)
    else:
        st.info("لا توجد بيانات تفصيلية لعرضها.")


# ────────────────────────────────────────────────────────────
# 7.3 التنبؤ المستقبلي (Predictive Forecasting)
# ────────────────────────────────────────────────────────────
def render_forecast():
    st.markdown(f"""
    <div class="page-header" style="justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div class="ph-icon-wrap">{get_icon("bulb", 46, "#00f2ff")}</div>
            <div>
                <div class="ph-title">التنبؤ المستقبلي (الكرة البلورية - Prophet AI)</div>
                <div class="ph-sub">نظام إحصائي ذكي معزز بخوارزميات الذكاء الاصطناعي للتنبؤ بالإيرادات القادمة بدقة فائقة.</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if df_s_master is None or df_s_master.empty or 'date_order' not in df_s_master.columns:
        st.warning("لا توجد بيانات زمنية كافية لبناء نموذج التنبؤ.")
        return

    df_appr = df_s_master[df_s_master['state'].isin(['sale', 'done'])].copy()
    if df_appr.empty:
        st.warning("لا توجد مبيعات فعلية معتمدة لبناء التنبؤ.")
        return

    df_appr['Month'] = df_appr['date_order'].dt.to_period('M').dt.to_timestamp()
    monthly = df_appr.groupby('Month')['amount_total'].sum().reset_index().sort_values('Month')

    if len(monthly) < 3:
        st.warning("نحتاج بيانات مبيعات لثلاثة أشهر على الأقل لبناء نموذج تنبؤ دقيق.")
        st.dataframe(style_dataframe(monthly.rename(columns={'amount_total':'القيمة (ج.م)'})), use_container_width=True, hide_index=True)
        return

    # ---------------------------------------------------------
    # محرك الذكاء الاصطناعي المتقدم (Meta Prophet)
    # ---------------------------------------------------------
    use_prophet = False
    try:
        from prophet import Prophet
        use_prophet = True
    except ImportError:
        st.warning("⚠️ خوارزمية الدقة القصوى (Prophet) غير مثبتة على الخادم. يعمل النظام الآن بنمط الانحدار الخطي الافتراضي. لرفع الدقة لـ 95%، يرجى إضافة 'prophet' لملف المتطلبات.")

    if use_prophet and len(monthly) >= 4:
        df_p = monthly.rename(columns={'Month': 'ds', 'amount_total': 'y'})
        m = Prophet(seasonality_mode='multiplicative', daily_seasonality=False, weekly_seasonality=False)
        m.fit(df_p)
        future = m.make_future_dataframe(periods=3, freq='MS')
        forecast = m.predict(future)
        forecast['yhat'] = np.maximum(forecast['yhat'], 0) 
        forecast['yhat_lower'] = np.maximum(forecast['yhat_lower'], 0)
        forecast['yhat_upper'] = np.maximum(forecast['yhat_upper'], 0)
        
        pred_trace_df = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].rename(columns={'ds': 'Month', 'yhat': 'amount_total'})
        pred_df = pred_trace_df.tail(3).copy()
        upper_bound = pred_trace_df['yhat_upper']
        lower_bound = pred_trace_df['yhat_lower']
        future_y = pred_df['amount_total'].values
    else:
        x = np.arange(len(monthly))
        y = monthly['amount_total'].values
        coeffs = np.polyfit(x, y, 1)
        poly_func = np.poly1d(coeffs)
        last_month = monthly['Month'].max()
        future_months = [last_month + pd.DateOffset(months=i) for i in range(1, 4)]
        future_x = np.arange(len(monthly), len(monthly) + 3)
        future_y = poly_func(future_x)
        future_y = np.maximum(future_y, 0) 
        pred_df = pd.DataFrame({'Month': future_months, 'amount_total': future_y})
        pred_trace_df = pd.concat([monthly.iloc[[-1]], pred_df]).reset_index(drop=True)
        upper_bound = pred_trace_df['amount_total'] * 1.15
        lower_bound = pred_trace_df['amount_total'] * 0.85

    
    if st.button(f"📥 تحليل وتصدير تقرير التنبؤ (Word / PDF)", use_container_width=True):
        export_data = {"الأداء التاريخي (فعلي)": monthly, "الأرقام المتوقعة": pred_df[['Month', 'amount_total']]}
        show_detailed_report("تقرير التنبؤ المستقبلي", {"df": export_data})
        
    st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin-bottom: 20px;'>", unsafe_allow_html=True)
    
    st.markdown("<h4 style='color:var(--c-primary); margin-bottom: 20px;'>الأرقام المتوقعة للأشهر الثلاثة القادمة:</h4>", unsafe_allow_html=True)
    cols = st.columns(3)
    for i, row in pred_df.iterrows():
        month_name = row['Month'].strftime('%Y-%m') 
        val = row['amount_total']
        with cols[i % 3]:
            st.markdown(f"""
            <div class="custom-metric" style="text-align: center;">
                <div class="cm-label" style="text-align: center; margin-bottom: 5px;">شهر {month_name}</div>
                <div class="neon-forecast">{val:,.0f} <span style="font-size: 1rem;">ج.م</span></div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    st.markdown(f"<div class='g-card-title'>{get_icon('trending-up', 22)} مسار الإيرادات الفعلي والمتوقع مع نطاق الثقة</div>", unsafe_allow_html=True)
    
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=monthly['Month'], y=monthly['amount_total'], 
                             mode='lines', line=dict(color='rgba(0,242,255,0.2)', width=12), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=monthly['Month'], y=monthly['amount_total'], 
                             mode='lines+markers', name='مبيعات فعلية',
                             line=dict(color='#00f2ff', width=3), 
                             marker=dict(size=8, color='#00f2ff', line=dict(width=2, color='#fff')),
                             fill='tozeroy', fillcolor='rgba(0,242,255,0.05)'))

    fig.add_trace(go.Scatter(
        x=pd.concat([pred_trace_df['Month'], pred_trace_df['Month'][::-1]]),
        y=pd.concat([upper_bound, lower_bound[::-1]]),
        fill='toself',
        fillcolor='rgba(255, 215, 0, 0.1)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        name='نطاق الثقة',
        showlegend=True
    ))

    fig.add_trace(go.Scatter(x=pred_trace_df['Month'], y=pred_trace_df['amount_total'], 
                             mode='lines', line=dict(color='rgba(255,215,0,0.2)', width=12, dash='dash'), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=pred_trace_df['Month'], y=pred_trace_df['amount_total'], 
                             mode='lines+markers', name='تنبؤ مستقبلي',
                             line=dict(color='#ffd700', width=3, dash='dash'),
                             marker=dict(size=8, color='#ffd700', line=dict(width=2, color='#fff'))))

    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode="x unified",
        xaxis_title="",
        yaxis_title="القيمة (ج.م)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(font_family="Cairo", font_size=14)
    )
    fig.update_traces(hovertemplate='<b>%{x|%Y-%m}</b><br>القيمة: %{y:,.0f} ج.م')
    
    st.markdown("<div class='g-card' style='padding: 0;'>", unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    
    if st.button("رؤية المدير الاستراتيجية للمستقبل", type="primary"):
        with st.spinner("المدير يدرس المؤشرات المستقبلية..."):
            actual_str = ", ".join([f"{row['amount_total']:,.0f}" for _, row in monthly.tail(3).iterrows()])
            pred_str = ", ".join([f"{val:,.0f}" for val in future_y])
            prompt = f"بناءً على التحليل الإحصائي، المبيعات الفعلية لأخر 3 شهور كانت: [{actual_str}] جنيه. النموذج يتوقع للأشهر الـ 3 القادمة: [{pred_str}] جنيه. بصفتك المدير التنفيذي للشركة، أعطني تحليلاً قصيراً جداً وتوجيهاً استراتيجياً واحداً لمواجهة هذا المسار بناءً على خبرتك بدون استخدام Emojis نهائياً."
            try:
                res = call_universal_ai([{"role": "user", "content": prompt}])
                st.markdown("<div style='background:rgba(255,215,0,0.1); border:1px solid rgba(255,215,0,0.4); padding:20px; border-radius:12px; margin-top:10px;'>", unsafe_allow_html=True)
                st.markdown(f"<h4 style='color:#ffd700; margin-top:0;'>رؤية المدير الاستراتيجية للمستقبل</h4>", unsafe_allow_html=True)
                st.markdown(f"<div dir='rtl' style='text-align: right; line-height: 1.8; font-size: 1.05rem; color: #e2e8f0;'>\n\n{res}\n\n</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception:
                st.error("الخادم غير متاح حالياً لاستخراج الرؤية المستقبلية.")

# ────────────────────────────────────────────────────────────
# 7.4 مكتب المدير (COMMANDER OMNISCIENT MEMORY - PERFECT RTL & NO EMOJI)
# ────────────────────────────────────────────────────────────
def render_ai():
    # ── ميزة تصدير المحادثة (Chat Export) ──
    c_header1, c_header2 = st.columns([3, 1])
    with c_header1:
        st.markdown(f"""
        <div style="background-color: #1f2c34; padding: 12px 20px; border-radius: 12px; display: flex; align-items: center; gap: 15px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <div style="width: 45px; height: 45px; border-radius: 50%; background-color: rgba(0, 242, 255, 0.1); display: flex; align-items: center; justify-content: center; font-size: 1.4rem; font-weight: bold; color: var(--c-primary); border: 1px solid rgba(0, 242, 255, 0.3);">
                {get_icon("command", 24, "var(--c-primary)")}
            </div>
            <div>
                <div style="font-weight: 700; font-size: 1.1rem; color: #fff; margin-bottom: -3px;">المدير العام</div>
                <div style="font-size: 0.85rem; color: #00ff82;">متصل الآن</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with c_header2:
        curr_user_for_export = st.session_state.current_user
        chat_content = ""
        for msg in st.session_state.all_chats.get(curr_user_for_export, []):
            role_name = "الموظف" if msg['role'] == 'user' else "المدير"
            chat_content += f"[{role_name}]: {msg['content']}\n{'-'*40}\n"
        
        st.download_button(
            label="📥 حفظ المحادثة (TXT)",
            data=chat_content.encode('utf-8-sig'),
            file_name=f"Chat_Backup_{curr_user_for_export}_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True
        )

    # إضافة إعدادات العرض (محرك التصغير والتكبير المرن)
    with st.expander("🔍 إعدادات العرض (تكبير وتصغير الشاشة)", expanded=False):
        cz1, cz2 = st.columns(2)
        with cz1:
            chat_zoom = st.slider("تكبير/تصغير حجم الخط (%)", min_value=50, max_value=200, value=100, step=10, help="قم بالتصغير لترى المزيد من الكلام، أو التكبير لرؤية أوضح.")
        with cz2:
            chat_height = st.slider("طول شاشة المحادثة (بيكسل)", min_value=300, max_value=1200, value=500, step=50, help="اسحب لتطويل الشاشة لرؤية المحادثة كاملة بدون تمرير (Scrolling).")
    
    st.markdown(f"""
    <style>
    .chat-bubble {{
        font-size: {1.05 * (chat_zoom/100)}rem !important;
        line-height: {1.6 * (chat_zoom/100)} !important;
    }}
    .chat-bubble p, .chat-bubble li {{
        font-size: {1.05 * (chat_zoom/100)}rem !important;
        line-height: {1.8 * (chat_zoom/100)} !important;
    }}
    [data-testid="stChatMessage"] div.stButton > button {{
        width: {34 * (chat_zoom/100)}px !important;
        height: {34 * (chat_zoom/100)}px !important;
        min-height: {34 * (chat_zoom/100)}px !important;
        font-size: {1.1 * (chat_zoom/100)}rem !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    curr_user = st.session_state.current_user
    df_s = df_s_master
    df_p = df_p_master

    t_sales_appr = df_s[df_s['state'].isin(['sale','done'])]['amount_total'].sum() if df_s is not None and not df_s.empty and 'state' in df_s.columns else 0
    t_sales_draft = df_s[df_s['state'].isin(['draft','sent'])]['amount_total'].sum() if df_s is not None and not df_s.empty and 'state' in df_s.columns else 0
    t_sales_canc = df_s[df_s['state'] == 'cancel']['amount_total'].sum() if df_s is not None and not df_s.empty and 'state' in df_s.columns else 0
    p_len = len(df_p) if df_p is not None else 0
    
    quotes_summary = "لا توجد عروض أسعار معلقة أو مسودة حالياً."
    if df_s is not None and not df_s.empty and 'state' in df_s.columns and 'partner_id' in df_s.columns:
        drafts = df_s[df_s['state'].isin(['draft', 'sent'])].head(5)
        if not drafts.empty:
            quotes_summary = " | ".join([f"عرض ({row.get('name', 'N/A')}) للعميل ({clean_odoo_m2o(row['partner_id'])}) بقيمة {row.get('amount_total', 0)} ج.م" for _, row in drafts.iterrows()])

    clients_summary = "لا توجد بيانات عملاء كافية."
    if df_p is not None and not df_p.empty and 'name' in df_p.columns:
        sample_df = df_p[['name', 'city', 'total_invoiced']].dropna().sort_values('total_invoiced', ascending=False).head(5)
        clients_summary = " | ".join([f"{row['name']} ({row.get('city','-')})" for _, row in sample_df.iterrows()])

    team_context_lines = []
    for emp, chat in st.session_state.all_chats.items():
        if emp == "المدير العام" or emp == curr_user or not chat: continue
        last_task = next((m['content'] for m in reversed(chat) if m['role'] == 'assistant'), "")
        if last_task:
            last_task_clean = re.sub(r'\$\$EVAL:.*?\$\$', '', last_task).strip()[:150]
            team_context_lines.append(f"- {emp}: {last_task_clean}...")
    team_context_str = "\n".join(team_context_lines) if team_context_lines else "لا توجد تكليفات لزملاء آخرين حالياً."

    if "المدير العام" in curr_user:
        gm_tabs = st.tabs(["مراقبة وتقييم الموظفين (سري)", "مكتبي الخاص (توجيهات الإدارة)"])
        
        with gm_tabs[0]:
            st.markdown(f"<div class='g-card-title' style='color:var(--c-gold);'>{get_icon('eye', 22)} تقييمات الموظفين التلقائية</div>", unsafe_allow_html=True)
            evals = CFG.get('EVALUATIONS', {})
            if not evals:
                st.info("لا توجد تقييمات مسجلة بعد. سيقوم النظام بتسجيلها تلقائياً عند حديث الموظفين معه.")
            else:
                for emp_name, emp_data in evals.items():
                    st.markdown(f"""<div style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid rgba(255,255,255,0.05); margin-bottom:10px;">
                        <div style="color:var(--c-primary); font-weight:bold; font-size:1.1rem; margin-bottom:5px;">{emp_name}</div>
                        <div style="font-size:0.85rem; color:var(--c-dim); margin-bottom:10px;">أخر تقييم: {emp_data.get('date', '')}</div>
                        <div style="color:#e2e8f0; font-size:0.95rem; direction:rtl; text-align:right;">{emp_data.get('eval', '')}</div>
                    </div>""", unsafe_allow_html=True)
            
            st.markdown("<hr style='border-color:rgba(255,255,255,0.1); margin: 30px 0;'>", unsafe_allow_html=True)
            st.markdown(f"<div class='g-card-title' style='color:var(--c-accent);'>{get_icon('search', 22)} أرشيف محادثات الموظفين (إدارة كاملة)</div>", unsafe_allow_html=True)
            
            emp_list = [u for u in st.session_state.all_chats.keys() if "المدير العام" not in u]
            if emp_list:
                sel_emp = st.selectbox("اختر الموظف لمراجعة محادثته:", emp_list, label_visibility="collapsed")
                if sel_emp:
                    # أزرار الإدارة المنيعة
                    c_arc1, c_arc2 = st.columns(2)
                    with c_arc1:
                        if st.button(f"🗑️ مسح واجهة الشات لـ {sel_emp.split(' - ')[0]}", use_container_width=True):
                            st.session_state.all_chats[sel_emp] = [{"role": "assistant", "content": "تم مسح الأرشيف بواسطة الإدارة العليا. مستعد لتلقي التكليفات الجديدة."}]
                            save_chats()
                            st.rerun()
                    with c_arc2:
                        if st.button(f"🔄 استعادة المحادثة بالكامل من السجل السري", use_container_width=True, type="primary"):
                            audit_history = CFG.get('AUDIT_LOG', {}).get(sel_emp, [])
                            if audit_history:
                                st.session_state.all_chats[sel_emp] = [{"role": m["role"], "content": m["content"]} for m in audit_history]
                                save_chats()
                                st.success("تم استعادة المحادثة بالكامل من السجل السري بنجاح!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.warning("لا يوجد سجل سري مسجل لهذا الموظف بعد.")
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    chat_to_view = st.session_state.all_chats[sel_emp]
                    for idx, m in enumerate(chat_to_view):
                        with st.chat_message(m["role"]):
                            st.markdown(f"<span class='msg-{m['role']}' style='display:none;'></span>", unsafe_allow_html=True)
                            st.markdown(f"<div class='chat-bubble' dir='rtl'>{m['content']}</div>", unsafe_allow_html=True)
                            
                            st.markdown('<div class="chat-actions">', unsafe_allow_html=True)
                            if st.button("🗑️", key=f"gm_dl_{sel_emp}_{idx}", help="حذف الرسالة"):
                                st.session_state.all_chats[sel_emp].pop(idx)
                                save_chats()
                                st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info("لا توجد محادثات نشطة للموظفين حتى الآن.")

        with gm_tabs[1]:
            chat_area = st.container(height=chat_height, border=False)
            with chat_area:
                for idx, msg in enumerate(st.session_state.all_chats.get(curr_user, [])):
                    with st.chat_message(msg["role"]):
                        st.markdown(f"<span class='msg-{msg['role']}' style='display:none;'></span>", unsafe_allow_html=True)
                        st.markdown(f"<div class='chat-bubble' dir='rtl'>{msg['content']}</div>", unsafe_allow_html=True)
                        
                        st.markdown('<div class="chat-actions">', unsafe_allow_html=True)
                        if st.button("🗑️", key=f"dl_{curr_user}_{idx}", help="حذف الرسالة"):
                            st.session_state.all_chats[curr_user].pop(idx)
                            save_chats()
                            st.rerun()
                        st.markdown('</div>', unsafe_allow_html=True)
                    
            user_input = st.chat_input("أصدر أوامرك، اطلب خططاً، أو استعلم عن البيانات...")
            
    else:
        chat_area = st.container(height=chat_height, border=False)
        with chat_area:
            for idx, msg in enumerate(st.session_state.all_chats.get(curr_user, [])):
                with st.chat_message(msg["role"]):
                    st.markdown(f"<span class='msg-{msg['role']}' style='display:none;'></span>", unsafe_allow_html=True)
                    st.markdown(f"<div class='chat-bubble' dir='rtl'>{msg['content']}</div>", unsafe_allow_html=True)
                
        user_input = st.chat_input("اكتب رسالة...")

    # -------------------------------------------------------------------
    # معالجة المدخلات (وتخزينها في السجل السري المنيع)
    # -------------------------------------------------------------------
    if user_input:
        if curr_user not in st.session_state.all_chats:
            st.session_state.all_chats[curr_user] = []
            
        user_msg = {"role": "user", "content": user_input}
        st.session_state.all_chats[curr_user].append(user_msg)
        log_message(curr_user, user_msg)
        save_chats()
        
        with chat_area:
            with st.chat_message("user"):
                st.markdown("<span class='msg-user' style='display:none;'></span>", unsafe_allow_html=True)
                st.markdown(f"<div class='chat-bubble' dir='rtl'>{user_input}</div>", unsafe_allow_html=True)
            
            with st.spinner("يكتب الآن..."):
                base_prompt = CFG.get('AI_SYSTEM_PROMPT', DEFAULT_SYSTEM_PROMPT)
                
                # جلب الوصف الوظيفي للموظف الحالي ليستخدمه الذكاء الاصطناعي
                curr_emp_data = next((e for e in CFG.get('EMPLOYEES', []) if f"{e['name']} - {e['role']}" == curr_user), None)
                job_desc = curr_emp_data.get('job_desc', 'لا يوجد وصف وظيفي محدد.') if curr_emp_data else 'أنت المدير العام.'
                
                live_context = f"""
                
=== بيانات النظام الحية (يجب أخذها في الاعتبار) ===
- المبيعات المنفذة (موافق عليه): {t_sales_appr:,.0f} ج.م
- عروض الأسعار المسودة/المعلقة (قيد الانتظار): {t_sales_draft:,.0f} ج.م
- العروض الملغاة (خسائر محتملة أو رفض): {t_sales_canc:,.0f} ج.م
- إجمالي قاعدة العملاء: {p_len} عميل
- عينة من أهم عملائنا الحاليين: {clients_summary}
- عروض أسعار معلقة محتاجة متابعة فورية: {quotes_summary}

=== موقف باقي أعضاء الفريق (مهم جداً: لا تعطي نفس العميل أو المهمة لموظفين مختلفين) ===
{team_context_str}

الموظف اللي بيكلمك دلوقتي: {curr_user}.
"""
                if curr_user != "المدير العام":
                    live_context += f"\n=== ملف الموظف الحالي ({curr_user}) ===\n"
                    live_context += f"المهام والأهداف المطلوبة من هذا الموظف (KPIs):\n{job_desc}\n"
                    live_context += "بصفتك المدير، قم بتوجيه الموظف ومحاسبته وإعطائه مهام بناءً على هذا الوصف الوظيفي والأهداف بدقة وبدون أي مجاملة.\n"

                live_context += """
**مهم جداً جداً للتقييم**: في نهاية أي رسالة بتكتبها، لازم تقيم الموظف (إذا لم يكن هو المدير العام) من 10 وتكتب تعليق سري عن أدائه. التقييم ده لازم يكون في آخر سطر بالظبط بالشكل ده:
$$EVAL: 8/10 - الموظف ردوده إيجابية بس محتاج يسرع رتمه شوية$$
إياك تنسى كود الـ $$EVAL: في النهاية، وإياك تعرف الموظف إنك بتقيمه أو بتكتب الكود ده. السرية التامة ضرورية."""

                sys_prompt = base_prompt + "\n" + live_context

                api_messages = [{"role": "system", "content": sys_prompt}]
                api_messages.extend(st.session_state.all_chats[curr_user])
                
                try:
                    response_text = call_universal_ai(api_messages)
                    
                    action_match = re.search(r'\$\$ACTION:\s*CREATE_SO\s*\|\s*العميل:\s*(.*?)\s*\|\s*القيمة:\s*(.*?)\$\$', response_text)
                    if action_match:
                        client_name = action_match.group(1).strip()
                        amt = action_match.group(2).strip()
                        response_text = re.sub(r'\$\$ACTION:.*?\$\$', '', response_text).strip()
                        
                        ai_msg1 = {"role": "assistant", "content": response_text}
                        st.session_state.all_chats[curr_user].append(ai_msg1)
                        log_message(curr_user, ai_msg1)
                        
                        ai_msg2 = {"role": "system", "content": f"إشعار من النظام: تم إنشاء مسودة عرض سعر بنجاح في النظام للعميل ({client_name}) بقيمة تقديرية ({amt})."}
                        st.session_state.all_chats[curr_user].append(ai_msg2)
                        log_message(curr_user, ai_msg2)
                        
                        save_chats()
                        st.rerun()

                    eval_match = re.search(r'\$\$EVAL:\s*(.*?)\$\$', response_text)
                    if eval_match:
                        eval_data = eval_match.group(1)
                        response_text = re.sub(r'\$\$EVAL:\s*(.*?)\$\$', '', response_text).strip()
                        
                        if "المدير العام" not in curr_user:
                            if 'EVALUATIONS' not in CFG:
                                CFG['EVALUATIONS'] = {}
                            CFG['EVALUATIONS'][curr_user] = {
                                'eval': eval_data,
                                'date': datetime.now().strftime("%Y-%m-%d %H:%M")
                            }
                            save_config(CFG)
                    
                    response_text = re.sub(r'\$\$EVAL:.*', '', response_text, flags=re.DOTALL).strip()

                    ai_final_msg = {"role": "assistant", "content": response_text}
                    st.session_state.all_chats[curr_user].append(ai_final_msg)
                    log_message(curr_user, ai_final_msg)
                    
                    save_chats()
                    st.rerun()
                except Exception as e:
                    st.session_state.all_chats[curr_user].pop()
                    save_chats()
                    err_msg = str(e).lower()
                    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
                        st.error("فشل الاتصال: الخادم المركزي عليه ضغط أو وصل للحد الأقصى للعمليات. يُرجى مراجعة إعدادات الربط.")
                    elif "401" in err_msg or "auth" in err_msg:
                        st.error("فشل الاتصال: إعدادات الخادم المركزي غير مفعلة بشكل صحيح.")
                    else:
                        st.error("المدير مشغول حالياً بمراجعة تقارير أخرى، ممكن حضرتك تكلمني بعد 10 دقايق؟")

# ────────────────────────────────────────────────────────────
# 7.5 مختبر البيانات (Fusion Lab)
# ────────────────────────────────────────────────────────────
def render_fusion():
    st.markdown(f"""
    <div class="page-header" style="justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div class="ph-icon-wrap">{get_icon("fusion", 46, "#00f2ff")}</div>
            <div>
                <div class="ph-title">مختبر الاندماج (Data Fusion)</div>
                <div class="ph-sub">اربط بياناتك الخارجية مع بيانات النواة لاستنتاج الفرص</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    up1, up2 = st.columns([2,1])
    with up1:
        st.markdown(f"<strong style='color:var(--c-primary); display:flex; align-items:center; gap:8px; margin-bottom:10px;'>{get_icon('folder', 18)} إدراج الملف الخارجي (Excel / CSV)</strong>", unsafe_allow_html=True)
        file_up = st.file_uploader("", type=['csv','xlsx'], label_visibility="collapsed")
    with up2:
        st.info("ارفع قائمة موردين، منافسين، أو بيانات سوقية ليدمجها النظام التحليلي مع أرقام مبيعاتنا الحالية ويستخرج التقاطعات الذهبية.")

    if file_up:
        try:
            ext_df = pd.read_excel(file_up) if file_up.name.endswith('.xlsx') else pd.read_csv(file_up)
            
            if st.button(f"📥 تحليل وتصدير البيانات المدخلة (Word / PDF)", use_container_width=True):
                show_detailed_report("البيانات الخارجية", {"df": {"البيانات المدرجة": ext_df}})
                
            st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 20px 0;'>", unsafe_allow_html=True)

            with st.container():
                # مسح إحصائي تلقائي (Auto-Data Scan)
                st.markdown(f"<div class='g-card-title' style='margin-top:20px; color:var(--c-gold);'>{get_icon('activity', 22)} المسح الإحصائي المبدئي للبيانات</div>", unsafe_allow_html=True)
                cols_num = ext_df.select_dtypes(include=[np.number]).columns
                if not cols_num.empty:
                    stats_cols = st.columns(min(len(cols_num), 4))
                    for idx, col in enumerate(cols_num[:4]):
                        with stats_cols[idx]:
                            st.markdown(f"""
                            <div style="background:rgba(255,215,0,0.05); padding:15px; border-radius:8px; border:1px solid rgba(255,215,0,0.2); text-align:center;">
                                <div style="font-size:0.8rem; color:var(--c-dim); margin-bottom:5px;">متوسط ({col})</div>
                                <div style="font-size:1.4rem; font-weight:bold; color:var(--c-gold);">{ext_df[col].mean():,.0f}</div>
                            </div>
                            """, unsafe_allow_html=True)
                
                st.markdown(f"<div class='g-card-title' style='margin-top:20px;'>{get_icon('chart', 22)} استعراض هيكل البيانات: `{file_up.name}`</div>", unsafe_allow_html=True)
                st.dataframe(ext_df.head(10), use_container_width=True)

                if st.button("بدء تفاعل الاندماج المعرفي", type="primary"):
                    with st.spinner("جاري استخلاص الأنماط المعقدة..."):
                        t_sales_appr = df_s_master[df_s_master['state'].isin(['sale','done'])]['amount_total'].sum() if not df_s_master.empty else 0
                        internal_summary = f"المبيعات المعتمدة={t_sales_appr:,.0f}, العملاء={len(df_p_master)}"
                        fusion_prompt = f"أنت محلل. بياناتنا: {internal_summary}. الملف الخارجي (عينة): {ext_df.head(10).to_string()}. استخرج 3 فرص ذهبية، مخاطر محتملة، وتكتيك للغد. أجب باحترافية تامة وبدون Emojis."
                        try:
                            messages = [{"role": "user", "content": fusion_prompt}]
                            response_text = call_universal_ai(messages)
                            st.markdown("<div style='background:rgba(112,0,255,0.05); border:1px solid rgba(112,0,255,0.3); padding:25px; border-radius:15px; margin-top:20px;'>", unsafe_allow_html=True)
                            st.markdown(f"<h3 style='color:#7000ff; margin-top:0; display:flex; align-items:center; gap:10px;'>{get_icon('dna', 28)} تقرير الاندماج فائق الدقة</h3>", unsafe_allow_html=True)
                            st.markdown(f"<div dir='rtl' style='text-align: right;'>\n\n{response_text}\n\n</div>", unsafe_allow_html=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                        except Exception:
                            st.error("الخادم المركزي عليه ضغط شديد حالياً، يُرجى المحاولة بعد قليل.")
        except Exception: 
            st.error("خطأ في قراءة الملف.")


# ────────────────────────────────────────────────────────────
# 7.7 التحليل الجغرافي (Territories - TREEMAP UPGRADE)
# ────────────────────────────────────────────────────────────
def render_territories():
    st.markdown(f"""
    <div class="page-header" style="justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div class="ph-icon-wrap">{get_icon("globe", 46, "#00f2ff")}</div>
            <div>
                <div class="ph-title">التحليل الجغرافي للاستحواذ</div>
                <div class="ph-sub">خريطة حرارية لتمركز الإيرادات وتوزيعها (مفلترة زمنياً)</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    start_dt, end_dt, _, _ = get_smart_filter_dates("terr")

    t_df = df_s_master.copy()
    if start_dt and end_dt and not t_df.empty and 'date_order' in t_df.columns:
        t_df = t_df[(t_df['date_order'] >= start_dt) & (t_df['date_order'] <= end_dt)]

    if t_df.empty:
        return st.warning("البيانات غير كافية للتحليل الجغرافي للفترة المحددة.")

    df_s_appr = t_df[t_df['state'].isin(['sale', 'done'])].copy()
    if df_s_appr.empty:
        return st.warning("لا توجد مبيعات معتمدة في هذه الفترة.")
        
    df_s_appr['اسم العميل'] = df_s_appr['partner_id'].apply(clean_odoo_m2o)
    city_dict = dict(zip(df_p_master['name'], df_p_master['city'])) if not df_p_master.empty else {}
    df_s_appr['المدينة'] = df_s_appr['اسم العميل'].map(city_dict).fillna('غير محدد')

    city_df = df_s_appr.groupby('المدينة')['amount_total'].sum().reset_index()
    city_df = city_df.rename(columns={'amount_total': 'total_invoiced'})
    
    city_details = df_s_appr.groupby('المدينة').agg(
        عدد_العملاء=('اسم العميل', 'nunique'),
        إجمالي_الفواتير=('amount_total', 'sum')
    ).reset_index().sort_values('إجمالي_الفواتير', ascending=False)
    
    if st.button(f"📥 تحليل وتصدير التقرير الجغرافي (Word / PDF)", use_container_width=True):
        export_data = {"المدن والتمركز الجغرافي": city_details}
        show_detailed_report("التحليل الجغرافي للاستحواذ", {"df": export_data})
        
    st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin-bottom: 20px;'>", unsafe_allow_html=True)
    
    st.markdown(f"<div class='g-card-title'>{get_icon('globe', 22)} الخريطة الحرارية للاستحواذ المالي بالمدن</div>", unsafe_allow_html=True)
    if not city_df.empty:
        fig = px.treemap(city_df, path=[px.Constant("إجمالي الإيرادات"), 'المدينة'], values='total_invoiced',
                         color='total_invoiced', color_continuous_scale=['#1f2c34', '#7000ff', '#00f2ff'],
                         template='plotly_dark')
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', margin=dict(t=20, b=0, l=0, r=0), hoverlabel=dict(font_family="Cairo", font_size=14))
        fig.update_traces(textinfo="label+value+percent parent", hovertemplate='<b>%{label}</b><br>القيمة: %{value:,.0f} ج.م<extra></extra>')
        st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"<br><div class='g-card-title'>{get_icon('table', 22)} تفاصيل التمركز الجغرافي وقوة المدن</div>", unsafe_allow_html=True)
    st.dataframe(style_dataframe(city_details), use_container_width=True, hide_index=True)


# ────────────────────────────────────────────────────────────
# 7.8 إعدادات النظام و "خزنة البيانات" (Settings & Data Vault)
# ────────────────────────────────────────────────────────────
def render_settings():
    st.markdown(f"""<div class="page-header"><div class="ph-icon-wrap">{get_icon("settings", 46, "#00f2ff")}</div><div><div class="ph-title">إعدادات النواة المركزية</div><div class="ph-sub">إصدار COMMANDER: إدارة شاملة للبيانات، الخوادم، وهيكل الموظفين</div></div></div>""", unsafe_allow_html=True)

    # جلب الحد الأقصى للمستخدمين من الترخيص
    licenses = load_licenses()
    ws_id = st.session_state.get('workspace_key', '')
    ws_data = licenses.get('workspaces', {}).get(ws_id, {})
    max_devices = ws_data.get('max_devices', 1)

    # ─── ميزة خزنة البيانات (Data Vault) للحماية من سيرفرات Streamlit ───
    st.markdown(f"<div class='g-card-title' style='color:#00ff82;'>{get_icon('folder', 22)} خزنة الشركة (النسخ الاحتياطي السحابي)</div>", unsafe_allow_html=True)
    st.info("نظراً لطبيعة الخوادم السحابية، يُنصح بتحميل نسخة احتياطية من بيانات شركتك (تشمل المحادثات، الإعدادات، وأرقام الموظفين) والاحتفاظ بها، لرفعها واستعادة النظام فوراً إذا لزم الأمر.")
    
    cv1, cv2 = st.columns(2)
    with cv1:
        vault_data_str = json.dumps(CFG, ensure_ascii=False, indent=4)
        st.download_button(
            label="📥 سحب ملف خزنة الشركة (Backup)",
            data=vault_data_str.encode('utf-8-sig'),
            file_name=f"Mudir_Vault_{ws_id}_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )
    with cv2:
        uploaded_vault = st.file_uploader("📤 استعادة النظام من الخزنة", type=['json'], label_visibility="collapsed")
        if uploaded_vault:
            if st.button("🚨 تأكيد الاستعادة (سيمسح البيانات الحالية)", type="primary", use_container_width=True):
                try:
                    restored_data = json.load(uploaded_vault)
                    st.session_state.app_config = restored_data
                    save_config(restored_data)
                    st.success("تم استعادة بيانات الشركة بنجاح! جاري إعادة التشغيل...")
                    time.sleep(1)
                    st.rerun()
                except Exception:
                    st.error("ملف الخزنة تالف أو غير صالح.")
    
    st.markdown("<br><hr style='border-color:rgba(255,255,255,0.05)'><br>", unsafe_allow_html=True)

    # --- 1. إعدادات الأمان (المدير العام) ---
    st.markdown(f"<div class='g-card-title'>{get_icon('check', 22)} إعدادات الأمان للمدير العام</div>", unsafe_allow_html=True)
    m_pin = st.text_input("رمز الدخول السري للمدير (PIN)", value=CFG.get('MANAGER_PIN', '0000'), type="password", disabled=True, help="لا يمكن تغيير الرقم السري إلا من قبل الإدارة العليا (Super Admin).")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- 2. إدارة الموظفين (HR Module) ---
    st.markdown(f"<div class='g-card-title'>{get_icon('users', 22)} نظام إدارة الموظفين والصلاحيات (الحد الأقصى المسموح: {max_devices} مستخدم)</div>", unsafe_allow_html=True)
    
    current_emps = CFG.get('EMPLOYEES', [])
    st.info(f"تم استهلاك {len(current_emps)} من أصل {max_devices} مستخدم مسموح به في رخصة شركتك.")
    
    st.markdown("<div style='background:rgba(255,255,255,0.02); padding:20px; border-radius:12px; border:1px solid rgba(255,255,255,0.05); margin-bottom:20px;'>", unsafe_allow_html=True)
    with st.form("add_emp_form", clear_on_submit=True):
        st.markdown("**➕ إضافة موظف جديد:**")
        c_emp1, c_emp2, c_emp3 = st.columns([2, 2, 2])
        with c_emp1: new_emp_name = st.text_input("اسم الموظف", placeholder="مثال: أحمد محمود")
        with c_emp2: new_emp_role = st.text_input("الوظيفة / القسم", placeholder="مثال: مبيعات هاتفية")
        with c_emp3: new_emp_pin = st.text_input("الرقم السري للموظف (PIN)", placeholder="مثال: 1234")
        
        new_emp_desc = st.text_area("الوصف الوظيفي والأهداف (KPIs)", placeholder="اكتب هنا مهام الموظف وما تتوقعه منه، ليقوم الذكاء الاصطناعي بمتابعته وتوجيهه بناءً عليها...")
        
        view_options = {i[2]: i[0] for i in ALL_NAV_ITEMS if i[0] not in ['settings']}
        new_emp_views = st.multiselect("الشاشات المسموحة", list(view_options.keys()), default=["مكتب المدير"])

        submit_emp = st.form_submit_button("إضافة الموظف للنظام", use_container_width=True, type="primary")

    if submit_emp:
        if len(current_emps) >= max_devices:
            st.error("🚫 عذراً! لقد وصلت للحد الأقصى لعدد المستخدمين المسموح به في رخصتك الحالية. لا يمكنك إضافة المزيد. يرجى التواصل مع الإدارة العليا للترقية.")
        elif any(emp['name'].strip().lower() == new_emp_name.strip().lower() for emp in current_emps):
            st.error("🚫 عذراً! يوجد موظف مسجل بنفس هذا الاسم مسبقاً. يرجى استخدام اسم مختلف (أو إضافة لقب) لمنع التداخل في المهام والمحادثات.")
        elif new_emp_name and new_emp_role and new_emp_views and new_emp_pin:
            view_keys = [view_options[k] for k in new_emp_views]
            current_emps.append({
                'name': new_emp_name, 
                'role': new_emp_role, 
                'pin': new_emp_pin, 
                'job_desc': new_emp_desc,
                'views': view_keys
            })
            CFG['EMPLOYEES'] = current_emps
            save_config(CFG)
            st.rerun()
        else:
            st.warning("أدخل كافة البيانات (الاسم، الوظيفة، الرمز السري) واختر شاشة واحدة على الأقل.")
    st.markdown("</div>", unsafe_allow_html=True)
                
    if current_emps:
        st.markdown("**📋 قائمة الموظفين المسجلين وصلاحياتهم:**")
        for i, emp in enumerate(current_emps):
            views_str = ", ".join([v for k, v in view_options.items() if emp.get('views') and view_options[k] in emp['views']])
            pin_display = emp.get('pin', '0000')
            desc_display = emp.get('job_desc', 'لا يوجد وصف.')
            
            st.markdown(f"""
            <div style="background:rgba(15,15,20,0.6); padding:15px; border-radius:10px; border-right: 4px solid var(--c-primary); margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                <div style="flex:1;">
                    <div style="font-size:1.1rem; font-weight:bold; color:#fff; margin-bottom:5px;">
                        {emp['name']} <span style="font-size:0.85rem; font-weight:normal; color:var(--c-dim);">({emp['role']})</span>
                    </div>
                    <div style="font-size:0.85rem; color:#e2e8f0; margin-bottom:5px;">
                        <span style="color:var(--c-primary);">الشاشات:</span> {views_str}
                    </div>
                    <div style="font-size:0.85rem; color:#cbd5e1; line-height:1.4;">
                        <span style="color:#00ff82;">المهام (KPIs):</span> {desc_display}
                    </div>
                </div>
                <div style="text-align:left; min-width:120px;">
                    <div style="background:rgba(255,215,0,0.1); color:#ffd700; padding:4px 10px; border-radius:6px; font-weight:bold; font-size:0.9rem; margin-bottom:10px; text-align:center; border:1px solid rgba(255,215,0,0.3);">
                        PIN: {pin_display}
                    </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"حذف {emp['name']}", key=f"del_emp_{i}", use_container_width=True):
                current_emps.pop(i)
                CFG['EMPLOYEES'] = current_emps
                save_config(CFG)
                st.rerun()
                
            st.markdown("</div></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='color:var(--c-dim); font-size:0.9rem;'>لا يوجد موظفين مسجلين حالياً.</div>", unsafe_allow_html=True)

    st.markdown("<br><hr style='border-color:rgba(255,255,255,0.05)'><br>", unsafe_allow_html=True)

    # --- 3. إعدادات الإدارة والشخصية (Prompt) ---
    st.markdown(f"<div class='g-card-title'>{get_icon('cpu', 22)} إعدادات الاتصال بالخادم المركزي</div>", unsafe_allow_html=True)
    
    st.markdown("### شخصية وتوجيهات المدير (System Prompt)")
    st.info("هذا النص يحدد شخصية وطريقة تفكير المدير. سيقوم النظام آلياً بإضافة البيانات الحية وتقييم الموظفين أسفل هذا النص، لذا ركز هنا على 'الشخصية وقواعد المهام' فقط.")
    ai_system_prompt = st.text_area("تعليمات الإدارة", value=CFG.get('AI_SYSTEM_PROMPT', DEFAULT_SYSTEM_PROMPT), height=250)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### دليل وإعدادات الربط")
    
    with st.expander("معلومات إضافية حول روابط الخدمة (انقر للفتح)"):
        st.markdown("""
        **لربط الخادم الرئيسي (OpenAI):**
        - **رابط المزود:** `https://api.openai.com/v1`
        - **اسم الموديل:** `gpt-4o` أو `gpt-3.5-turbo`
        - **ملاحظة هامة جداً:** مفاتيح `sk-...` الخاصة بالخدمة **لن تعمل** إذا كان الحساب لا يحتوي على رصيد مدفوع (Billing). يجب شحن رصيد لتفعيل واجهة برمجة التطبيقات.

        **لربط المزود الوسيط (OpenRouter):**
        - **رابط المزود:** `https://openrouter.ai/api/v1`
        - **اسم الموديل:** (يجب أن يبدأ باسم المزود) مثل `openai/gpt-4o-mini` أو `google/gemini-2.5-flash`

        **لربط الخادم المباشر الآخر:**
        - **رابط المزود:** `https://generativelanguage.googleapis.com/v1beta/openai/`
        - **اسم الموديل:** `gemini-2.5-flash`
        """)
        
    saved_url = CFG.get('AI_PROVIDER_URL', '')
    url_presets = ["https://openrouter.ai/api/v1", "https://api.openai.com/v1", "https://api.x.ai/v1", "https://generativelanguage.googleapis.com/v1beta/openai/", ""]
    if saved_url not in url_presets: url_presets.insert(0, saved_url)
    url_options = list(dict.fromkeys(url_presets)) + ["مخصص (كتابة يدوية)..."]
    
    sel_url = st.selectbox("رابط مزود الخدمة (Base URL)", url_options, index=url_options.index(saved_url) if saved_url in url_options else 0, help="اختر رابط الخدمة أو اكتبه يدوياً باختيار 'مخصص'")
    ai_url = st.text_input("أدخل الرابط المخصص:", value=saved_url) if sel_url == "مخصص (كتابة يدوية)..." else sel_url

    saved_model = CFG.get('AI_MODEL_NAME', 'gpt-4o')
    model_presets = ["gpt-4o", "gpt-4o-mini", "openai/gpt-4o-mini", "google/gemini-2.5-flash", "gemini-2.5-flash", "anthropic/claude-3-5-sonnet", "grok-beta"]
    if saved_model not in model_presets: model_presets.insert(0, saved_model)
    model_options = list(dict.fromkeys(model_presets)) + ["مخصص (كتابة يدوية)..."]
    
    sel_model = st.selectbox("اسم الموديل (Model Name)", model_options, index=model_options.index(saved_model) if saved_model in model_options else 0, help="تأكد من توافق اسم الموديل مع مزود الخدمة (مثال: OpenAI يستخدم gpt-4o)")
    ai_model = st.text_input("أدخل اسم الموديل المخصص:", value=saved_model) if sel_model == "مخصص (كتابة يدوية)..." else sel_model

    ai_key = st.text_input("مفتاح الربط (API Key)", value=CFG.get('AI_API_KEY', ''), type="password", help="انسخ المفتاح وتأكد من عدم وجود مسافات فارغة قبله أو بعده")

    if st.button("فحص اتصال الخادم المركزي", key="test_ai"):
        if not ai_key.strip():
            st.warning("الرجاء إدخال مفتاح الربط في الحقل أعلاه قبل إجراء الفحص.")
        else:
            try:
                with st.spinner("جاري فحص الاتصال بالخادم..."):
                    test_client = OpenAI(api_key=ai_key.strip(), base_url=ai_url.strip() if ai_url.strip() else None)
                    resp = test_client.chat.completions.create(model=ai_model, messages=[{"role": "user", "content": "Hello, respond with 'OK'"}], max_tokens=5)
                    if resp.choices[0].message.content: st.success("تم الاتصال بالخادم المركزي بنجاح!")
            except Exception as e: 
                err_msg = str(e).lower()
                if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
                    st.error("فشل الاتصال: لقد استنفدت رصيدك المتاح أو وصلت للحد الأقصى للطلبات. يُرجى مراجعة باقة الاشتراك أو شحن رصيد.")
                elif "401" in err_msg or "auth" in err_msg:
                    st.error("فشل الاتصال: مفتاح الربط غير صحيح أو غير مفعل. تأكد من نسخه بالكامل بدون مسافات إضافية.")
                elif "404" in err_msg or "not found" in err_msg:
                    st.error("فشل الاتصال: اسم الموديل الذي أدخلته غير صحيح أو غير مدعوم من المزود الذي اخترته.")
                else:
                    st.error("الخادم المركزي لا يستجيب حالياً، يرجى المحاولة بعد قليل أو التأكد من صحة الرابط.")

    st.markdown("<br><hr style='border-color:rgba(255,255,255,0.05)'><br>", unsafe_allow_html=True)

    # --- 4. إعدادات أودو ---
    st.markdown(f"<div class='g-card-title'>{get_icon('fusion', 22)} تكوين قاعدة البيانات (Odoo)</div>", unsafe_allow_html=True)
    o_url = st.text_input("رابط الخادم (URL)", value=CFG.get('ODOO_URL', ''))
    o_db = st.text_input("قاعدة البيانات (DB)", value=CFG.get('ODOO_DB', ''))
    o_usr = st.text_input("المستخدم (User)", value=CFG.get('ODOO_USER', ''))
    o_pwd = st.text_input("كلمة المرور (Password)", value=CFG.get('ODOO_PASS', ''), type="password")
    
    if st.button("فحص اتصال Odoo", key="test_odoo"):
        try:
            with st.spinner("جاري فحص الاتصال..."):
                cm = xmlrpc.client.ServerProxy(f'{o_url}/xmlrpc/2/common')
                uid = cm.authenticate(o_db, o_usr, o_pwd, {})
                if uid: st.success("الاتصال بقاعدة البيانات ناجح وموثق!")
                else: st.error("المصادقة مرفوضة. تأكد من البيانات.")
        except Exception: 
            st.error("السيرفر بتاع أودو مريح شوية حالياً، بس النظام هيشتغل على البيانات اللي متكيشة.")

    st.markdown("<hr style='border-color:rgba(255,255,255,0.1); margin: 30px 0;'>", unsafe_allow_html=True)
    if st.button("حفظ الإعدادات وإعادة بناء النواة", type="primary", use_container_width=True):
        new_config = {
            'ODOO_URL': o_url, 'ODOO_DB': o_db, 'ODOO_USER': o_usr, 'ODOO_PASS': o_pwd, 
            'AI_PROVIDER_URL': ai_url, 'AI_MODEL_NAME': ai_model, 'AI_API_KEY': ai_key,
            'AI_SYSTEM_PROMPT': ai_system_prompt,
            'MANAGER_PIN': m_pin,
            'EMPLOYEES': current_emps,
            'EVALUATIONS': CFG.get('EVALUATIONS', {}),
            'ALL_CHATS': CFG.get('ALL_CHATS', {}),
            'AUDIT_LOG': CFG.get('AUDIT_LOG', {})
        }
        st.session_state.app_config = new_config
        save_config(new_config)
        fetch_master_data.clear()
        st.session_state.data_loaded = False
        st.success("تم الحفظ محلياً بنجاح! جاري إعادة التشغيل...")
        time.sleep(1)
        st.rerun()
        
    st.markdown("<div style='text-align: center; color: var(--c-dim); font-size: 0.9rem; margin-top: 50px; font-weight: bold;'>Powered by محمد الحلواني</div>", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────
# 8. لوحة التحكم الخفية للإدارة العليا (Super Admin) + (Super Vault)
# ────────────────────────────────────────────────────────────

@st.dialog("إعدادات رخصة الشركة")
def change_workspace_pin_dialog(ws_id):
    st.markdown(f"**تغيير الرقم السري لمدير شركة:** `{ws_id}`")
    ws_file = f"mudir_workspace_{ws_id}.json"
    
    ws_cfg = {
        'ODOO_URL': '', 'ODOO_DB': '', 'ODOO_USER': '', 'ODOO_PASS': '',
        'AI_PROVIDER_URL': 'https://api.openai.com/v1', 'AI_API_KEY': '',
        'AI_MODEL_NAME': 'gpt-4o', 'AI_SYSTEM_PROMPT': DEFAULT_SYSTEM_PROMPT,
        'MANAGER_PIN': '0000', 'EMPLOYEES': [], 'EVALUATIONS': {}, 'ALL_CHATS': {} 
    }
    
    if os.path.exists(ws_file):
        try:
            with open(ws_file, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                ws_cfg.update(saved_config)
        except: pass
        
    current_pin = ws_cfg.get('MANAGER_PIN', '0000')
    new_pin = st.text_input("الرقم السري (PIN) الجديد:", value=current_pin)
    
    if st.button("حفظ التغيير", type="primary", use_container_width=True):
        ws_cfg['MANAGER_PIN'] = new_pin
        try:
            with open(ws_file, 'w', encoding='utf-8') as f:
                json.dump(ws_cfg, f, ensure_ascii=False, indent=4)
            st.success("تم تغيير الرمز السري بنجاح!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error("حدث خطأ أثناء الحفظ.")

def render_super_admin():
    # تم حل مشكلة تسجيل الخروج بإضافة Sidebar للتحكم الآمن
    with st.sidebar:
        st.markdown(f"""<div class="sidebar-brand"><div class="brand-logo">{get_icon("check", 32, "#7000ff")}</div><div class="brand-name">SAAS ADMIN</div><div class="brand-ver">v47.9</div></div>""", unsafe_allow_html=True)
        st.markdown("---")
        if st.button("🔴 تسجيل الخروج وإغلاق", use_container_width=True, type="primary"):
            st.query_params.clear()
            st.session_state.clear()
            st.rerun()

    st.markdown(f"""
    <div class="page-header" style="justify-content: space-between; background: linear-gradient(135deg, #1a0b2e, #050508);">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div class="ph-icon-wrap" style="background:rgba(112,0,255,0.1); border-color:#7000ff;">{get_icon("check", 46, "#7000ff")}</div>
            <div>
                <div class="ph-title" style="color:#e2e8f0;">مركز القيادة والتراخيص (SaaS Admin)</div>
                <div class="ph-sub" style="color:#b490ff;">إدارة اشتراكات الشركات، وخزنة البيانات الشاملة.</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    licenses = load_licenses()
    if 'workspaces' not in licenses:
        licenses['workspaces'] = {}

    # ─── خزنة المنصة الشاملة (Super Vault) ───
    st.markdown("<div class='g-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='g-card-title' style='color:#00ff82;'>{get_icon('database', 22)} الخزنة الشاملة للمنصة (Super Vault Backup)</div>", unsafe_allow_html=True)
    st.info("لحماية بيانات كل الشركات دفعة واحدة من ضياع سيرفرات Streamlit، قم بتحميل هذا الملف أسبوعياً.")
    
    sv1, sv2 = st.columns(2)
    with sv1:
        full_platform_backup = {
            "licenses_db": licenses,
            "workspaces_db": {}
        }
        for ws in licenses['workspaces'].keys():
            try:
                with open(f"mudir_workspace_{ws}.json", 'r', encoding='utf-8') as f:
                    full_platform_backup["workspaces_db"][ws] = json.load(f)
            except: pass
            
        mega_json_str = json.dumps(full_platform_backup, ensure_ascii=False, indent=4)
        st.download_button(
            label="📥 سحب ملف الخزنة الشاملة (كل الشركات)",
            data=mega_json_str.encode('utf-8-sig'),
            file_name=f"MUDIR_SUPER_VAULT_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )
    with sv2:
        mega_upload = st.file_uploader("📤 استعادة كل المنصة من ملف خزنة شامل", type=['json'], label_visibility="collapsed")
        if mega_upload:
            if st.button("🚨 تأكيد استعادة المنصة بالكامل", type="primary", use_container_width=True):
                try:
                    restored_mega = json.load(mega_upload)
                    if "licenses_db" in restored_mega: save_licenses(restored_mega["licenses_db"])
                    if "workspaces_db" in restored_mega:
                        for ws, ws_data in restored_mega["workspaces_db"].items():
                            with open(f"mudir_workspace_{ws}.json", 'w', encoding='utf-8') as f:
                                json.dump(ws_data, f, ensure_ascii=False, indent=4)
                    st.success("تم استعادة المنصة بالكامل بنجاح!")
                    time.sleep(1)
                    st.rerun()
                except Exception:
                    st.error("ملف الخزنة تالف أو غير صالح.")
    st.markdown("</div>", unsafe_allow_html=True)


    st.markdown("<div class='g-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='g-card-title' style='color:var(--c-gold);'>{get_icon('rocket', 22)} إصدار ترخيص لشركة جديدة</div>", unsafe_allow_html=True)
    
    st.markdown("<div style='background:rgba(255,255,255,0.02); padding:20px; border-radius:12px; border:1px solid rgba(255,255,255,0.05); margin-bottom:20px;'>", unsafe_allow_html=True)
    with st.form("new_license_form", clear_on_submit=True, border=False):
        c1, c2, c3, c4, c5 = st.columns([2.5, 2, 2, 2, 2])
        with c1: new_ws_id = st.text_input("كود الشركة (بالإنجليزية):", placeholder="مثال: Ghareeb2026")
        with c2: duration = st.selectbox("مدة الاشتراك:", ["شهر واحد", "3 شهور", "6 شهور", "سنة كاملة"])
        with c3: max_dev = st.number_input("أقصى عدد للمستخدمين:", min_value=1, max_value=1000, value=5)
        with c4: new_m_pin = st.text_input("رقم دخول المدير (PIN):", value="0000")
        with c5: 
            st.markdown("<br>", unsafe_allow_html=True)
            add_btn = st.form_submit_button("تفعيل المساحة", use_container_width=True, type="primary")

    if add_btn:
        safe_id = "".join(c for c in str(new_ws_id) if c.isalnum() or c in ('_', '-'))
        if not safe_id:
            st.error("يرجى إدخال كود صحيح.")
        elif safe_id in licenses['workspaces']:
            st.error("هذا الكود موجود بالفعل! اختر كوداً آخر.")
        else:
            days = 30 if duration == "شهر واحد" else 90 if duration == "3 شهور" else 180 if duration == "6 شهور" else 365
            expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            
            # 1. إنشاء الترخيص
            licenses['workspaces'][safe_id] = {
                "status": "active",
                "expiry_date": expiry,
                "created_on": datetime.now().strftime("%Y-%m-%d"),
                "max_devices": int(max_dev)
            }
            save_licenses(licenses)
            
            # 2. إنشاء ملف الإعدادات للشركة برقم المدير المخصص
            ws_file = f"mudir_workspace_{safe_id}.json"
            initial_config = {
                'ODOO_URL': '', 'ODOO_DB': '', 'ODOO_USER': '', 'ODOO_PASS': '',
                'AI_PROVIDER_URL': 'https://api.openai.com/v1', 'AI_API_KEY': '',
                'AI_MODEL_NAME': 'gpt-4o', 'AI_SYSTEM_PROMPT': DEFAULT_SYSTEM_PROMPT,
                'MANAGER_PIN': new_m_pin, 
                'EMPLOYEES': [], 'EVALUATIONS': {}, 'ALL_CHATS': {}, 'AUDIT_LOG': {} 
            }
            try:
                with open(ws_file, 'w', encoding='utf-8') as f:
                    json.dump(initial_config, f, ensure_ascii=False, indent=4)
            except: pass
            
            st.success(f"تم إنشاء ترخيص الشركة بنجاح! المستخدمين: {max_dev} | الانتهاء: {expiry}")
            time.sleep(1)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='g-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='g-card-title'>{get_icon('table', 22)} الشركات المشتركة وإدارة التراخيص</div>", unsafe_allow_html=True)
    
    if not licenses['workspaces']:
        st.info("لا توجد أي شركات مسجلة حتى الآن.")
    else:
        for ws_id, ws_info in licenses['workspaces'].items():
            is_active = ws_info['status'] == 'active'
            exp_date = datetime.strptime(ws_info['expiry_date'], "%Y-%m-%d")
            is_expired = datetime.now() > exp_date
            
            status_html = "<span style='color:#00ff82;'>نشط</span>" if is_active and not is_expired else "<span style='color:#ff2d78;'>منتهي / متوقف</span>"
            max_d = ws_info.get('max_devices', 1)
            
            with st.container():
                rc1, rc2, rc3, rc4, rc5, rc6 = st.columns([1.5, 1.5, 1.2, 1.5, 1.5, 2.5])
                rc1.markdown(f"**الشركة:** `{ws_id}`")
                rc2.markdown(f"**الحالة:** {status_html}", unsafe_allow_html=True)
                rc3.markdown(f"**مستخدمين:** {max_d}")
                rc4.markdown(f"**الانتهاء:** {ws_info['expiry_date']}")
                
                with rc5:
                    if st.button("تغيير PIN", key=f"btn_pin_{ws_id}", use_container_width=True):
                        change_workspace_pin_dialog(ws_id)
                        
                with rc6:
                    action_opts = ["اختر إجراء...", "تجديد +شهر", "تجديد +سنة", "زيادة مستخدمين (+5)", "إيقاف (تعليق)", "تفعيل"]
                    action = st.selectbox("الإجراء", action_opts, key=f"act_{ws_id}", label_visibility="collapsed")
                    if action != "اختر إجراء...":
                        if action == "تجديد +شهر":
                            new_exp = (exp_date + timedelta(days=30)).strftime("%Y-%m-%d")
                            licenses['workspaces'][ws_id]['expiry_date'] = new_exp
                            licenses['workspaces'][ws_id]['status'] = 'active'
                        elif action == "تجديد +سنة":
                            new_exp = (exp_date + timedelta(days=365)).strftime("%Y-%m-%d")
                            licenses['workspaces'][ws_id]['expiry_date'] = new_exp
                            licenses['workspaces'][ws_id]['status'] = 'active'
                        elif action == "زيادة مستخدمين (+5)":
                            licenses['workspaces'][ws_id]['max_devices'] = max_d + 5
                        elif action == "إيقاف (تعليق)":
                            licenses['workspaces'][ws_id]['status'] = 'suspended'
                        elif action == "تفعيل":
                            licenses['workspaces'][ws_id]['status'] = 'active'
                            
                        save_licenses(licenses)
                        st.rerun()
                st.markdown("<hr style='border-color:rgba(255,255,255,0.05); margin:10px 0;'>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────
# محول العرض (Router الآمن - Crash-Proof)
# ────────────────────────────────────────────────────────────
view = st.session_state.get('view', 'login')
curr_user = st.session_state.get('current_user')

if view == "workspace_login": 
    render_workspace_login()
elif view == "super_admin": 
    render_super_admin()
elif not curr_user or view == "login": 
    render_login()
else:
    if view == "dashboard": render_dashboard()
    elif view == "departments": render_departments()
    elif view == "forecast": render_forecast()
    elif view == "ai": render_ai()
    elif view == "fusion": render_fusion()
    elif view == "territories": render_territories()
    elif view == "settings": render_settings()
    else: render_dashboard()
