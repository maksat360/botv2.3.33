"""
V2 MES System — Генерация PDF с кириллицей
"""

import os
from fpdf import FPDF
from config import FONTS_DIR


class PDF(FPDF):
    """PDF-документ с поддержкой кириллицы"""

    def __init__(self):
        super().__init__()
        # Добавляем шрифт с кириллицей
        font_path = os.path.join(FONTS_DIR, "DejaVuSans.ttf")
        if os.path.exists(font_path):
            self.add_font("DejaVu", "", font_path, uni=True)
            self.add_font("DejaVu", "B", font_path, uni=True)  # жирный
        else:
            # Если шрифта нет, используем стандартный
            pass

    def header(self):
        if hasattr(self, "font_family") and "DejaVu" in str(self.font_family):
            self.set_font("DejaVu", "", 10)
            self.cell(0, 10, "V2 MES System", 0, 1, "C")

    def footer(self):
        self.set_y(-15)
        if hasattr(self, "font_family") and "DejaVu" in str(self.font_family):
            self.set_font("DejaVu", "", 8)
        self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", 0, 0, "C")


def generate_salary_pdf(employee_name: str, month: str, year: int, amount: float) -> str:
    """Сгенерировать PDF-справку о зарплате"""
    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    font_path = os.path.join(FONTS_DIR, "DejaVuSans.ttf")
    if os.path.exists(font_path):
        pdf.set_font("DejaVu", "", 16)
        pdf.cell(0, 20, "Справка о зарплате", 0, 1, "C")

        pdf.set_font("DejaVu", "", 12)
        pdf.cell(0, 10, f"Сотрудник: {employee_name}", 0, 1)
        pdf.cell(0, 10, f"Период: {month} {year}", 0, 1)
        pdf.cell(0, 10, f"Итого: {amount:,.0f} сом", 0, 1)
    else:
        pdf.cell(0, 20, f"Salary: {employee_name}", 0, 1, "C")
        pdf.cell(0, 10, f"Period: {month} {year}", 0, 1)
        pdf.cell(0, 10, f"Total: {amount:,.0f}", 0, 1)

    output_path = os.path.join("cloud_storage", "Отчёты", f"salary_{employee_name}_{month}_{year}.pdf")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path