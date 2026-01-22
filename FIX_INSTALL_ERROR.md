# حل مشكلة externally-managed-environment

## المشكلة
عند تشغيل `pip install` تظهر رسالة خطأ:
```
error: externally-managed-environment
```

## الحل السريع

### الطريقة 1: استخدام start.sh (موصى به)
```bash
bash start.sh
```
السكريبت سيقوم بإنشاء virtual environment تلقائياً وحل المشكلة.

### الطريقة 2: يدوياً
```bash
# 1. إنشاء virtual environment
python3 -m venv venv

# 2. تفعيل virtual environment
source venv/bin/activate  # Linux/Mac
# أو
venv\Scripts\activate  # Windows

# 3. تثبيت المتطلبات
pip install -r requirements.txt

# 4. تشغيل Panel
cd panel
python app.py
```

### الطريقة 3: استخدام setup.sh
```bash
bash setup.sh
bash start.sh
```

## لماذا يحدث هذا؟
- Python 3.11+ يمنع التثبيت المباشر على النظام
- الحل هو استخدام virtual environment معزول
- هذا أفضل للأمان وتجنب تعارض المكتبات

## التحقق من نجاح الحل
بعد تفعيل virtual environment، يجب أن ترى:
```bash
(venv) user@host:~/provisioning-platform$
```

الآن يمكنك تشغيل المنصة بدون مشاكل!
