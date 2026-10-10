import asyncio
import random
import uuid
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete

# If run directly as a script, ensure current folder is in python path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.session import AsyncSessionLocal, init_db
from db.models import Complaint
from config import settings
from timeutils import utcnow

DEMO_COMPLAINTS_DATA = [
    # --- Urdu Script (Overpricing) ---
    {
        "transcript_raw": "آلو مارکیٹ میں دو سو روپے کلو بیچ رہے ہیں جبکہ سرکاری لسٹ میں سو روپے ہے۔ غریب بندہ کہاں جائے؟",
        "detected_language": "Urdu",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Potato",
        "item_canonical_id": "aloo",
        "unit": "kg",
        "reported_price": 200.0,
        "official_price": 100.0,
        "location_area": "Raja Bazaar, Rawalpindi",
        "shop_name": "Madina Cash & Carry",
        "native_response": "آپ کی شکایت موصول ہو چکی ہے۔ پرائس کنٹرول مجسٹریٹ کو کارروائی کے لیے مطلع کر دیا گیا ہے۔ شکریہ۔",
        "status": "Investigating",
        "days_ago": 1,
        "confidence": 0.96
    },
    {
        "transcript_raw": "پیاز ڈیڑھ سو روپے کلو دے رہے ہیں جی نائن مرکز میں، کوئی چیک کرنے والا نہیں ہے۔",
        "detected_language": "Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Onion",
        "item_canonical_id": "pyaaz",
        "unit": "kg",
        "reported_price": 150.0,
        "official_price": 120.0,
        "location_area": "G-9 Markaz, Islamabad",
        "shop_name": "Bismillah General Store",
        "native_response": "آپ کی شکایت موصول ہو چکی ہے۔ مجاز اتھارٹی کو کارروائی کے لیے بھیج دیا گیا ہے۔ آپ کا شکریہ۔",
        "status": "Pending",
        "days_ago": 2,
        "confidence": 0.94
    },
    {
        "transcript_raw": "ٹماٹر ڈھائی سو روپے کلو کر دیا ہے آبپارہ مارکیٹ میں، سرکاری ریٹ ڈیڑھ سو ہے۔",
        "detected_language": "Urdu",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Tomato",
        "item_canonical_id": "tamatar",
        "unit": "kg",
        "reported_price": 250.0,
        "official_price": 150.0,
        "location_area": "Aabpara Market G-6, Islamabad",
        "shop_name": "Al-Madina Sabzi Shop",
        "native_response": "آپ کی شکایت موصول ہو گئی ہے۔ سپیشل پرائس مجسٹریٹ کو نوٹس جاری کر دیا گیا ہے۔",
        "status": "Resolved",
        "days_ago": 3,
        "confidence": 0.98
    },
    {
        "transcript_raw": "چینی ایک سو ساٹھ روپے کلو بیچ رہے ہیں جبکہ نوٹیفائیڈ ریٹ ایک سو چالیس ہے۔",
        "detected_language": "Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Low",
        "item_name": "Sugar",
        "item_canonical_id": "chini",
        "unit": "kg",
        "reported_price": 160.0,
        "official_price": 140.0,
        "location_area": "F-10 Markaz, Islamabad",
        "shop_name": "Punjab Traders",
        "native_response": "آپ کی شکایت درج کر لی گئی ہے۔ دکاندار کو وارننگ جاری کی جا رہی ہے۔",
        "status": "Pending",
        "days_ago": 4,
        "confidence": 0.95
    },
    {
        "transcript_raw": "تندور والا روٹی پچیس روپے کی بیچ رہا ہے، کہتا ہے آٹا مہنگا ملا ہے۔ سرکاری ریٹ پندرہ روپے ہے۔",
        "detected_language": "Urdu",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Tandoori Roti",
        "item_canonical_id": "roti",
        "unit": "piece",
        "reported_price": 25.0,
        "official_price": 15.0,
        "location_area": "Tench Bhata, Rawalpindi",
        "shop_name": "Khyber Tandoor",
        "native_response": "شکایت پر فوری کارروائی کی جا رہی ہے۔ مجسٹریٹ روانہ کر دیا گیا ہے۔",
        "status": "Investigating",
        "days_ago": 5,
        "confidence": 0.97
    },
    {
        "transcript_raw": "مرغی کا گوشت ساڑھے سات سو روپے کلو دے رہے ہیں راجہ بازار میں، سرکاری ریٹ چھ سو پچاس ہے۔",
        "detected_language": "Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Chicken Meat",
        "item_canonical_id": "chicken_meat",
        "unit": "kg",
        "reported_price": 750.0,
        "official_price": 650.0,
        "location_area": "Raja Bazaar, Rawalpindi",
        "shop_name": "Madina Cash & Carry",
        "native_response": "آپ کی شکایت موصول ہو چکی ہے۔ پرائس کنٹرول مجسٹریٹ کو کارروائی کے لیے بھیج دیا گیا ہے۔",
        "status": "Pending",
        "days_ago": 6,
        "confidence": 0.93
    },

    # --- Roman Urdu (Overpricing & Gouging) ---
    {
        "transcript_raw": "Bhai Raja Bazaar mein Madina store wala doodh 280 rupay liter de raha hai, official rate 210 hai bohat zulm hai.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Fresh Milk",
        "item_canonical_id": "doodh",
        "unit": "litre",
        "reported_price": 280.0,
        "official_price": 210.0,
        "location_area": "Raja Bazaar, Rawalpindi",
        "shop_name": "Madina Cash & Carry",
        "native_response": "Aap ki shikayat darj kar li gayi hai. Price Control Magistrate ko karwai ke liye bhaij diya gaya hai. Shukriya.",
        "status": "Pending",
        "days_ago": 1,
        "confidence": 0.96
    },
    {
        "transcript_raw": "Commercial Market mein anday teen sau assi rupay darjan bech rahay hain, rate list per 300 likha hai.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Farm Eggs",
        "item_canonical_id": "anday",
        "unit": "dozen",
        "reported_price": 380.0,
        "official_price": 300.0,
        "location_area": "Commercial Market, Rawalpindi",
        "shop_name": "Al-Makkah Milk Shop",
        "native_response": "Aap ki shikayat darj kar li gayi hai. Vendor ke khilaf inquiry shuru ho gayi hai.",
        "status": "Investigating",
        "days_ago": 2,
        "confidence": 0.95
    },
    {
        "transcript_raw": "G-9 Karachi Company mein cooking oil paanch sau assi rupay litre de rahe hain, rate list board bhi chupa dia hai.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Cooking Oil",
        "item_canonical_id": "cooking_oil",
        "unit": "litre",
        "reported_price": 580.0,
        "official_price": 480.0,
        "location_area": "G-9 Markaz, Islamabad",
        "shop_name": "Bismillah General Store",
        "native_response": "Aap ki shikayat darj kar li gayi hai. Price inspection team ko dispatch kar diya gaya hai.",
        "status": "Pending",
        "days_ago": 3,
        "confidence": 0.93
    },
    {
        "transcript_raw": "Bara gosht barah sau rupay kilo mang raha hai Saddar mein, rate 850 hona chahiye.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Beef (without bone)",
        "item_canonical_id": "beef",
        "unit": "kg",
        "reported_price": 1200.0,
        "official_price": 850.0,
        "location_area": "Saddar, Rawalpindi",
        "shop_name": "Pindi Meat Corner",
        "native_response": "Shikayat darj kar li gayi hai. AC Saddar ki team shop check karegi.",
        "status": "Resolved",
        "days_ago": 4,
        "confidence": 0.97
    },
    {
        "transcript_raw": "Chawal basmati chaar sau rupay kilo de rahe hain Barakahu mandi mein.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Basmati Rice",
        "item_canonical_id": "chawal_basmati",
        "unit": "kg",
        "reported_price": 400.0,
        "official_price": 320.0,
        "location_area": "Barakahu, Islamabad",
        "shop_name": "Al-Rehman Karyana",
        "native_response": "Aap ki shikayat darj kar li gayi hai. Mandi inspector ko ittila de di gayi hai.",
        "status": "Pending",
        "days_ago": 5,
        "confidence": 0.92
    },
    {
        "transcript_raw": "Daal chana 330 rupay kilo di hai dukandar ne I-10 Sabzi Mandi mein.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Gram Pulse (Daal Chana)",
        "item_canonical_id": "daal_chana",
        "unit": "kg",
        "reported_price": 330.0,
        "official_price": 260.0,
        "location_area": "I-10 Sabzi Mandi, Islamabad",
        "shop_name": "SubhanAllah Wholesale",
        "native_response": "Shikayat darj ho chuki hai. PERA enforcement team mutaharik ho chuki hai.",
        "status": "Investigating",
        "days_ago": 7,
        "confidence": 0.91
    },

    # --- Punjabi (Dialect & Shahmukhi) ---
    {
        "transcript_raw": "تہاڈے ریٹ لسٹ وچ دہی دا ریٹ دو سو تریہہ اے، اے کمرشل مارکیٹ آلا تن سو روپے منگ رہیا اے۔",
        "detected_language": "Punjabi",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Yogurt",
        "item_canonical_id": "dahi",
        "unit": "kg",
        "reported_price": 300.0,
        "official_price": 230.0,
        "location_area": "Commercial Market, Rawalpindi",
        "shop_name": "Al-Makkah Milk Shop",
        "native_response": "تہاڈی شکایت درج ہو گئی اے۔ پرائس کنٹرول مجسٹریٹ نوں کارروائی واسطے بھیج دتا گیا اے۔ مہربانی۔",
        "status": "Pending",
        "days_ago": 2,
        "confidence": 0.94
    },
    {
        "transcript_raw": "Dukaan aale ne atta 20 kilo thaila 3300 da ditta ae, larki aakhdi sarkari rate 2750 ae.",
        "detected_language": "Punjabi",
        "category": "PERA - Overpricing",
        "urgency": "Low",
        "item_name": "Wheat Flour 20kg Bag",
        "item_canonical_id": "atta_20kg",
        "unit": "bag",
        "reported_price": 3300.0,
        "official_price": 2750.0,
        "location_area": "Tench Bhata, Rawalpindi",
        "shop_name": "Bhai Jan Flour Store",
        "native_response": "Tuhadi shikayat darj ho gayi ae. Intizamiya nu karwai waste bhej ditta gaya ae. Mehrbani.",
        "status": "Investigating",
        "days_ago": 6,
        "confidence": 0.90
    },
    {
        "transcript_raw": "Kela do sau rupay darjan bech rahe ne Saddar bazaar ch, baqi jagah dedh sau ae.",
        "detected_language": "Punjabi",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Banana",
        "item_canonical_id": "kela",
        "unit": "dozen",
        "reported_price": 200.0,
        "official_price": 150.0,
        "location_area": "Saddar, Rawalpindi",
        "shop_name": "Fruit Stall 44",
        "native_response": "Tuhadi shikayat darj ho gayi ae. Assistant Commissioner nu notify keeta gaya ae.",
        "status": "Resolved",
        "days_ago": 8,
        "confidence": 0.91
    },

    # --- Pashto ---
    {
        "transcript_raw": "پیر ودھائی منڈی کی دوکاندار ٹماٹر دو سوه شل روپۍ کلو خرڅوی، نرخ لسٹ نشته.",
        "detected_language": "Pashto",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Tomato",
        "item_canonical_id": "tamatar",
        "unit": "kg",
        "reported_price": 220.0,
        "official_price": 150.0,
        "location_area": "Pir Wadhai Mandi, Rawalpindi",
        "shop_name": "Khyber Traders",
        "native_response": "ستاسو شکایت ثبت شو او مجاز پرائس مجسټریټ ته د څیړنې لپاره واستول شو. مننه.",
        "status": "Pending",
        "days_ago": 3,
        "confidence": 0.93
    },
    {
        "transcript_raw": "Dukaandar pa doodh 270 rupay litre اخلی، سرکاری نرخ 210 روپے دے.",
        "detected_language": "Pashto",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Fresh Milk",
        "item_canonical_id": "doodh",
        "unit": "litre",
        "reported_price": 270.0,
        "official_price": 210.0,
        "location_area": "G-9 Markaz, Islamabad",
        "shop_name": "Shinwari Dairy",
        "native_response": "ستاسو شکایت په بریالیتوب سره ثبت شو او اړوندې ادارې ته واستول شو. مننه.",
        "status": "Investigating",
        "days_ago": 5,
        "confidence": 0.92
    },

    # --- English ---
    {
        "transcript_raw": "Vendor in F-10 Markaz is charging 2400 PKR per kg for mutton against the notified ceiling of 1800.",
        "detected_language": "English",
        "category": "PERA - Overpricing",
        "urgency": "Medium",
        "item_name": "Mutton (Goat)",
        "item_canonical_id": "mutton",
        "unit": "kg",
        "reported_price": 2400.0,
        "official_price": 1800.0,
        "location_area": "F-10 Markaz, Islamabad",
        "shop_name": "Islamabad Premium Cuts",
        "native_response": "Your complaint has been successfully registered and forwarded to the district price enforcement authorities. Thank you.",
        "status": "Pending",
        "days_ago": 1,
        "confidence": 0.98
    },
    {
        "transcript_raw": "Shop in F-6 Super Market selling brown bread for 200 PKR when plain double roti notified price is 130.",
        "detected_language": "English",
        "category": "PERA - Overpricing",
        "urgency": "High",
        "item_name": "Bread (Double Roti)",
        "item_canonical_id": "double_roti",
        "unit": "pack",
        "reported_price": 200.0,
        "official_price": 130.0,
        "location_area": "F-6 Super Market, Islamabad",
        "shop_name": "Super Bakers",
        "native_response": "Your complaint regarding bread price overcharge has been forwarded to ICT Administration.",
        "status": "Investigating",
        "days_ago": 4,
        "confidence": 0.95
    },

    # --- Food Safety (PFA) ---
    {
        "transcript_raw": "دودھ میں کیمیکل اور پانی کی کھلی ملاوٹ ہے، بچوں کا پیٹ خراب ہو گیا ہے۔ راجہ بازار کے اس دکان کو سیل کریں۔",
        "detected_language": "Urdu",
        "category": "PFA - Food Safety",
        "urgency": "High",
        "item_name": "Adulterated Milk",
        "item_canonical_id": "doodh",
        "unit": "litre",
        "reported_price": 0.0,
        "official_price": 210.0,
        "location_area": "Raja Bazaar, Rawalpindi",
        "shop_name": "Madina Cash & Carry",
        "native_response": "پنجاب فوڈ اتھارٹی کو ایمرجنسی نوٹس بھیج دیا گیا ہے۔ انسپکشن ٹیم نمونے لینے روانہ ہو رہی ہے۔",
        "status": "Investigating",
        "days_ago": 2,
        "confidence": 0.97
    },
    {
        "transcript_raw": "Baking unit in Commercial Market using expired oil and rat droppings found near flour sacks.",
        "detected_language": "English",
        "category": "PFA - Food Safety",
        "urgency": "High",
        "item_name": "Unhygienic Bakery",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "Commercial Market, Rawalpindi",
        "shop_name": "Paradise Sweets & Bakers",
        "native_response": "Your complaint has been forwarded with High Urgency to Punjab Food Authority (PFA) vigilance squad.",
        "status": "Investigating",
        "days_ago": 3,
        "confidence": 0.96
    },
    {
        "transcript_raw": "G-9 Karachi company hotel mein baasi aur badbudaar chicken ka salan khilaya ja raha hai.",
        "detected_language": "Roman Urdu",
        "category": "PFA - Food Safety",
        "urgency": "High",
        "item_name": "Spoiled Food",
        "item_canonical_id": "chicken_meat",
        "unit": "kg",
        "reported_price": 0.0,
        "official_price": 650.0,
        "location_area": "G-9 Markaz, Islamabad",
        "shop_name": "Usmania Tikka & Karahi",
        "native_response": "Punjab Food Authority aur ICT Health inspection team ko dispatch kar diya gaya hai.",
        "status": "Resolved",
        "days_ago": 5,
        "confidence": 0.94
    },
    {
        "transcript_raw": "Aabpara market ki dukaan se kharab daal masoor mili hai jis mein keere chal rahe thay.",
        "detected_language": "Roman Urdu",
        "category": "PFA - Food Safety",
        "urgency": "Medium",
        "item_name": "Insect Infested Pulses",
        "item_canonical_id": "daal_masoor",
        "unit": "kg",
        "reported_price": 0.0,
        "official_price": 280.0,
        "location_area": "Aabpara Market G-6, Islamabad",
        "shop_name": "Madina Karyana",
        "native_response": "Aap ki shikayat darj kar li gayi hai. Food safety inspectors stock check karein ge.",
        "status": "Pending",
        "days_ago": 7,
        "confidence": 0.93
    },

    # --- Municipal Infrastructure (CDA / WASA) ---
    {
        "transcript_raw": "جی نائن مرکز میں سکول کے سامنے مین ہول کھلا ہے اور گٹر ابل رہا ہے، بچے گر سکتے ہیں۔",
        "detected_language": "Urdu",
        "category": "Municipal - Infrastructure",
        "urgency": "High",
        "item_name": "Open Gutter / Sewer Overflow",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "G-9 Markaz, Islamabad",
        "shop_name": None,
        "native_response": "شکایت سی ڈی اے اور ایم سی آئی سیوریج کنٹرول ڈویژن کو فوری کارروائی کے لیے بھیج دی گئی ہے۔",
        "status": "Investigating",
        "days_ago": 1,
        "confidence": 0.98
    },
    {
        "transcript_raw": "Commercial market Satellite Town road completely dug up, WASA water pipeline leaking for two weeks.",
        "detected_language": "English",
        "category": "Municipal - Infrastructure",
        "urgency": "High",
        "item_name": "Leaking Water Main",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "Commercial Market, Rawalpindi",
        "shop_name": None,
        "native_response": "Grievance dispatched to WASA Rawalpindi emergency repair cell.",
        "status": "Pending",
        "days_ago": 2,
        "confidence": 0.96
    },
    {
        "transcript_raw": "Raja Bazaar kachra kundi se badboo aa rahi hai, teen din se kooda nahi uthaya gaya.",
        "detected_language": "Roman Urdu",
        "category": "Municipal - Infrastructure",
        "urgency": "Medium",
        "item_name": "Garbage Heap",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "Raja Bazaar, Rawalpindi",
        "shop_name": None,
        "native_response": "Rawalpindi Waste Management Company (RWMC) ko complaint assign kar di gayi hai.",
        "status": "Resolved",
        "days_ago": 4,
        "confidence": 0.95
    },
    {
        "transcript_raw": "PWD Road street lights totally dark at night, causing accidents and street crimes.",
        "detected_language": "English",
        "category": "Municipal - Infrastructure",
        "urgency": "Medium",
        "item_name": "Broken Street Lights",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "PWD Islamabad",
        "shop_name": None,
        "native_response": "Your complaint has been forwarded to CDA Electrical Engineering wing.",
        "status": "Pending",
        "days_ago": 6,
        "confidence": 0.92
    },
    {
        "transcript_raw": "F-10 Markaz public toilet completely broken, water dripping everywhere.",
        "detected_language": "English",
        "category": "Municipal - Infrastructure",
        "urgency": "Low",
        "item_name": "Public Facility Maintenance",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "F-10 Markaz, Islamabad",
        "shop_name": None,
        "native_response": "Forwarded to CDA Directorate of Municipal Administration (DMA).",
        "status": "Pending",
        "days_ago": 9,
        "confidence": 0.89
    },

    # --- Edge Cases & Needs Review ---
    {
        "transcript_raw": "Mandi mein ajeeb hisaab hai sab kuch mehnga kar dia hai samajh nahi araha.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Low",
        "item_name": "Assorted Commodities",
        "item_canonical_id": None,
        "unit": "unit",
        "reported_price": 0.0,
        "official_price": 0.0,
        "location_area": "I-10 Sabzi Mandi, Islamabad",
        "shop_name": "Unspecified Vendor",
        "native_response": "Aap ki shikayat darj kar li gayi hai. Tafseelat ke liye human reviewer dekh raha hai.",
        "status": "Pending",
        "days_ago": 1,
        "confidence": 0.45,
        "needs_review": True
    },
    {
        "transcript_raw": "Doodh lia tha lekin hisaab nahi samjha.",
        "detected_language": "Roman Urdu",
        "category": "PERA - Overpricing",
        "urgency": "Low",
        "item_name": "Fresh Milk",
        "item_canonical_id": "doodh",
        "unit": "litre",
        "reported_price": 0.0,
        "official_price": 210.0,
        "location_area": "G-9 Markaz, Islamabad",
        "shop_name": "Bismillah General Store",
        "native_response": "Aap ki shikayat darj hai. Price verify karne ke liye call ki ja sakti hai.",
        "status": "Pending",
        "days_ago": 4,
        "confidence": 0.50,
        "needs_review": True
    }
]


async def seed_database(db: AsyncSession) -> int:
    """Inserts demo grievances with realistic time spreads and coordinates."""
    # Delete existing complaints
    await db.execute(delete(Complaint))
    await db.commit()

    created_count = 0
    now = utcnow()

    # Pre-calculated area coordinates
    COORDS = {
        "Raja Bazaar, Rawalpindi": (33.6167, 73.0560),
        "G-9 Markaz, Islamabad": (33.6897, 73.0298),
        "Aabpara Market G-6, Islamabad": (33.7077, 73.0851),
        "F-10 Markaz, Islamabad": (33.6961, 73.0135),
        "F-6 Super Market, Islamabad": (33.7297, 73.0765),
        "Tench Bhata, Rawalpindi": (33.5855, 73.0336),
        "Commercial Market, Rawalpindi": (33.6338, 73.0694),
        "Saddar, Rawalpindi": (33.5960, 73.0520),
        "Barakahu, Islamabad": (33.7431, 73.1762),
        "I-10 Sabzi Mandi, Islamabad": (33.6552, 73.0365),
        "Pir Wadhai Mandi, Rawalpindi": (33.6185, 73.0450),
        "PWD Islamabad": (33.5880, 73.1490),
    }

    # Generate additional variants to exceed 40 complaints
    full_dataset = list(DEMO_COMPLAINTS_DATA)
    # Duplicate some items across different days to reach 42 complaints
    for i in range(15):
        base = random.choice(DEMO_COMPLAINTS_DATA[:15])
        clone = dict(base)
        clone["days_ago"] = random.randint(1, 13)
        # Small price variation
        if clone.get("reported_price") and clone["reported_price"] > 0:
            clone["reported_price"] = clone["reported_price"] + random.choice([-10, 10, 20, 0])
        full_dataset.append(clone)

    for item in full_dataset:
        days_ago = item.get("days_ago", random.randint(0, 10))
        hour_offset = random.randint(1, 23)
        minute_offset = random.randint(1, 59)
        created_at = now - timedelta(days=days_ago, hours=hour_offset, minutes=minute_offset)

        rep_p = item.get("reported_price", 0.0)
        off_p = item.get("official_price", 0.0)
        diff_pkr = round(rep_p - off_p, 2) if (rep_p and off_p) else 0.0
        pct_over = round(((rep_p - off_p) / off_p) * 100.0, 1) if (off_p and off_p > 0 and rep_p > off_p) else 0.0

        area = item.get("location_area")
        lat, lng = COORDS.get(area, (33.6844, 73.0479))

        routing_agency = "Punjab Enforcement & Regulatory Authority (PERA) / ICT Administration"
        helpline = settings.PERA_ENFORCEMENT_HELPLINE
        if item.get("category") == "PFA - Food Safety":
            routing_agency = "Punjab Food Authority (PFA)"
            helpline = settings.PFA_FOOD_SAFETY_HELPLINE
        elif item.get("category") == "Municipal - Infrastructure":
            routing_agency = "Capital Development Authority (CDA / MCI) / WASA Rawalpindi"
            helpline = settings.CDA_MUNICIPAL_HELPLINE

        complaint = Complaint(
            id=str(uuid.uuid4()),
            created_at=created_at,
            updated_at=created_at,
            audio_filename=f"voice_note_{random.randint(1000, 9999)}.wav" if random.random() > 0.3 else None,
            audio_duration_seconds=round(random.uniform(3.5, 18.0), 1),
            transcript_raw=item["transcript_raw"],
            detected_language=item["detected_language"],
            category=item["category"],
            urgency=item["urgency"],
            status=item.get("status", "Pending"),
            extraction_confidence=item.get("confidence", 0.90),
            needs_review=item.get("needs_review", False),
            item_name=item.get("item_name"),
            item_canonical_id=item.get("item_canonical_id"),
            unit=item.get("unit"),
            reported_price=rep_p,
            official_price=off_p,
            price_difference_pkr=diff_pkr,
            percentage_overcharge=pct_over,
            native_response=item["native_response"],
            routing_agency=routing_agency,
            helpline_reference=helpline,
            location_area=area,
            shop_name=item.get("shop_name"),
            lat=lat,
            lng=lng
        )
        db.add(complaint)
        created_count += 1

    await db.commit()
    print(f"Successfully seeded {created_count} demo complaints.")
    return created_count


async def main():
    print("Initializing database...")
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_database(session)


if __name__ == "__main__":
    asyncio.run(main())

