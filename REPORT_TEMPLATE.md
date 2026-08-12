# ETL Lab Report

Student ID: __________  Name: __________

## 1. Data Quality Problems Found

- **qty ติดลบ** — เช่น O0007 มี qty = -2
- **discount_pct เกิน 100%** — เช่น O0021 มี discount_pct = 150
- **order_date ว่าง/ขาดหาย** — เช่น O0034 ไม่มีวันที่
- **unit_price ติดลบ** — เช่น O0091 มี unit_price = -100.0
- **รูปแบบวันที่ในคอลัมน์ order_date ไม่สม่ำเสมอ** ต้องรองรับหลายฟอร์แมต (`%Y/%m/%d`, `%Y-%m-%d`, `%d/%m/%Y`, `%d-%b-%Y`)
- **สถานะออเดอร์ที่ไม่ใช่ paid/completed** (pending, cancelled) เป็นสาเหตุการ reject ที่พบมากที่สุด
- **order_id ซ้ำ** ในตาราง orders (ตัด duplicate โดยเก็บแถวแรกไว้)
- **customer_id / product_id ที่ไม่มีอยู่จริง** ในข้อมูลอ้างอิง เช่น customer_id `C999`, product_id `P999` ปรากฏในไฟล์ raw แต่ในรอบนี้ออเดอร์เหล่านั้นถูกตัดออกไปก่อนแล้วด้วยเงื่อนไขสถานะ จึงยังไม่มี reject ที่มีสาเหตุ unknown_customer/unknown_product เกิดขึ้นจริงในรันนี้
- **province และ email ที่ว่างหรือไม่ตรงรูปแบบ** ในไฟล์ customers.csv

## 2. Cleaning / Transformation Rules

- **customers**: ทำ province ให้เป็นตัวพิมพ์เล็ก แล้ว map ผ่าน `PROVINCE_MAP`, ถ้า map ไม่เจอให้เป็น `"Unknown"`; email ที่ว่างแทนที่ด้วย `unknown@example.com`; ตัด duplicate โดยยึด customer_id แรกที่เจอ
- **products**: flatten JSON ซ้อน (`category.name` → category, `pricing.price` → price); category ว่าง/None ให้เป็น `"Unknown"`; ลบ comma ออกจากราคาแล้วแปลงเป็นตัวเลข (แปลงไม่ได้ = NaN); ตัด duplicate โดยยึด product_id แรกที่เจอ
- **orders**: แปลง status เป็นตัวพิมพ์เล็ก, แปลง qty/unit_price/discount_pct เป็นตัวเลข, parse order_date แบบลองหลายฟอร์แมตตามลำดับ, ตัด duplicate order_id
- **กรองแถวที่ใช้ได้**: qty > 0, unit_price > 0, discount_pct อยู่ในช่วง 0–100, order_date parse สำเร็จ — ที่เหลือ reject เป็น `invalid_order_fields`
- **กรองสถานะ**: เก็บเฉพาะ status ที่เป็น `paid` หรือ `completed` — ที่เหลือ reject เป็น `status_not_paid_or_completed`
- **join กับ customers**: ออเดอร์ที่ customer_id ไม่พบใน dim_customer จะ reject เป็น `unknown_customer`
- **join กับ products**: ออเดอร์ที่ product_id ไม่พบใน dim_product จะ reject เป็น `unknown_product`
- **คำนวณยอดขาย**: `gross_amount = qty * unit_price`, `discount_amount = gross_amount * discount_pct / 100`, `sales_amount = gross_amount - discount_amount` (ใช้ unit_price ที่บันทึกในออเดอร์จริง ไม่ใช่ price จาก dim_product ซึ่งเป็นแค่ข้อมูลอ้างอิง)

## 3. Rejected Records

จำนวน: **80 แถว**

เหตุผลหลัก:
- `status_not_paid_or_completed` — 76 แถว (ส่วนใหญ่ที่สุด สถานะเป็น pending หรือ cancelled)
- `invalid_order_fields` — 4 แถว (qty ติดลบ, discount_pct เกิน 100%, order_date ว่าง, unit_price ติดลบ อย่างละ 1 แถว)
- `unknown_customer` / `unknown_product` — 0 แถว ในรอบรันนี้

## 4. ETL Validation

จากผลรัน `python3 -m src.main` ล่าสุด:

- Valid transformed rows: **100**
- Warehouse rows: **100**
- Duplicate order_id: **0**
- Source total sales: **192,074.66**
- Warehouse total sales: **192,074.66**
- Validation status: **PASS**

## 5. Idempotency Test

จำนวน fact_sales หลัง run ครั้งที่ 1: **100**

จำนวน fact_sales หลัง run ครั้งที่ 2: **100**

อธิบายผล: รันซ้ำสองครั้ง (16:08:31 และ 16:14:32) ได้ `warehouse_rows` เท่ากับ 100 ทั้งสองครั้ง และ `warehouse_total_sales` เท่ากับ 192,074.66 เท่ากันทุกครั้ง แสดงว่า pipeline เป็น idempotent — การรันซ้ำไม่ทำให้ข้อมูลใน fact_sales ซ้ำซ้อนหรือเพิ่มจำนวนขึ้น (load.py มีการ replace/upsert ข้อมูลแทนการ insert ทับซ้ำ)
