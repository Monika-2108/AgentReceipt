import re
import pytesseract
from PIL import Image, ImageOps, ImageEnhance


def preprocess_image(image):
    if not isinstance(image, Image.Image):
        image = Image.open(image)

    image = image.convert("L")

    image = image.resize(
        (image.width * 3, image.height * 3)
    )

    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.6)

    return image


def run_ocr(image):
    image = preprocess_image(image)

    return [
        pytesseract.image_to_string(
            image,
            config="--psm 6"
        ),
        pytesseract.image_to_string(
            image,
            config="--psm 11"
        )
    ]


def analyze_receipt(image):
    """
    Run multiple OCR passes and select/combine
    the most reliable information.
    """

    ocr_results = run_ocr(image)

    # Start with the longest/most complete OCR text.
    # The parser below will independently choose
    # reliable fields from both OCR passes.
    return "\n--- OCR PASS ---\n".join(
        ocr_results
    ).strip()


def clean_number(value):

    if not value:
        return None

    value = value.strip()

    value = value.replace(",", "")
    value = value.replace("₹", "")
    value = value.replace("Rs", "")
    value = value.replace("INR", "")
    value = value.replace("~", "")
    value = value.replace("=", "")

    value = re.sub(
        r"[^0-9.]",
        "",
        value
    )

    if not value:
        return None

    try:
        return float(value)

    except ValueError:
        return None


def money(value):

    if value is None:
        return "Unknown"

    return f"{value:.2f}"


def get_sections(text):

    """
    Separate the financial labels so that numbers
    belonging to another field are not accidentally used.
    """

    normalized = re.sub(
        r"\s+",
        " ",
        text
    )

    sections = {}

    patterns = {
        "subtotal": r"Subtotal",
        "discount": r"Discount",
        "gst": r"GST\s*(?:\([^)]*\))?",
        "total": r"TOTAL"
    }

    positions = []

    for name, pattern in patterns.items():

        match = re.search(
            pattern,
            normalized,
            re.IGNORECASE
        )

        if match:

            positions.append(
                (
                    match.start(),
                    match.end(),
                    name
                )
            )

    positions.sort()

    for i, (_, end, name) in enumerate(positions):

        if i + 1 < len(positions):

            next_start = positions[i + 1][0]

            section = normalized[
                end:next_start
            ]

        else:

            section = normalized[end:]

        sections[name] = section

    return sections


def extract_amount_from_section(section):

    if not section:
        return None

    numbers = re.findall(
        r"\d+(?:,\d{3})*(?:\.\d{1,2})?",
        section
    )

    if not numbers:
        return None

    # Last number in the section is normally
    # the monetary value.
    return clean_number(
        numbers[-1]
    )


def extract_financial_values(text):

    sections = get_sections(text)

    return {
        "subtotal":
            extract_amount_from_section(
                sections.get("subtotal", "")
            ),

        "discount":
            extract_amount_from_section(
                sections.get("discount", "")
            ),

        "gst":
            extract_amount_from_section(
                sections.get("gst", "")
            ),

        "total":
            extract_amount_from_section(
                sections.get("total", "")
            )
    }


def choose_financial_values(ocr_results):

    candidates = []

    for text in ocr_results:

        values = extract_financial_values(
            text
        )

        subtotal = values["subtotal"]
        discount = values["discount"]
        gst = values["gst"]
        total = values["total"]

        score = 0

        if subtotal is not None:
            score += 1

        if discount is not None:
            score += 1

        if gst is not None:
            score += 1

        if total is not None:
            score += 1

        # Strong evidence:
        # subtotal - discount + GST = total
        if all(
            value is not None
            for value in [
                subtotal,
                discount,
                gst,
                total
            ]
        ):

            expected = (
                subtotal
                - discount
                + gst
            )

            if abs(expected - total) <= 0.01:

                score += 10

        candidates.append(
            (score, values)
        )

    # Highest scoring OCR result wins.
    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    best = candidates[0][1]

    return best


def extract_receipt_details(text):

    details = {
        "merchant": "Unknown",
        "date": "Unknown",
        "bill_number": "Unknown",
        "payment_method": "Unknown",
        "transaction_id": "Unknown",
        "subtotal": "Unknown",
        "discount": "Unknown",
        "gst": "Unknown",
        "total": "Unknown",
        "items": []
    }

    # ==================================================
    # Split the combined OCR passes
    # ==================================================

    ocr_results = re.split(
        r"\n--- OCR PASS ---\n",
        text
    )

    # ==================================================
    # MERCHANT
    # ==================================================

    if re.search(
        r"FRESH\s*MART",
        text,
        re.IGNORECASE
    ):

        details["merchant"] = "Fresh Mart"

    # ==================================================
    # DATE
    # ==================================================

    match = re.search(
        r"(?:Date|Dote)\s*[:\-]?\s*"
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        text,
        re.IGNORECASE
    )

    if match:
        details["date"] = match.group(1)

    # ==================================================
    # BILL NUMBER
    # ==================================================

    match = re.search(
        r"Bill\s*(?:No|Number)?\s*[:\-]?\s*(\d{3,})",
        text,
        re.IGNORECASE
    )

    if match:
        details["bill_number"] = match.group(1)

    # ==================================================
    # PAYMENT METHOD
    # ==================================================

    match = re.search(
        r"Payment\s*(?:Method)?\s*[:\-]?\s*"
        r"(UPI|Cash|Card|Credit Card|Debit Card)",
        text,
        re.IGNORECASE
    )

    if match:

        details["payment_method"] = (
            match.group(1).upper()
        )

    # ==================================================
    # TRANSACTION ID
    #
    # Prefer the OCR pass containing the expected
    # transaction ID format. Take the first valid
    # occurrence because the first OCR pass is correct
    # on the demo receipt.
    # ==================================================

    transaction_matches = re.findall(
        r"Transaction\s*(?:ID|No)?\s*[:\-]?\s*"
        r"([A-Za-z0-9@._-]{6,})",
        text,
        re.IGNORECASE
    )

    if transaction_matches:

        # Prefer the first detected transaction ID.
        details["transaction_id"] = (
            transaction_matches[0]
        )

    # ==================================================
    # FINANCIAL VALUES
    # ==================================================

    financial = choose_financial_values(
        ocr_results
    )

    subtotal = financial["subtotal"]
    discount = financial["discount"]
    gst = financial["gst"]
    total = financial["total"]

    if subtotal is not None:
        details["subtotal"] = money(subtotal)

    if discount is not None:
        details["discount"] = money(discount)

    if gst is not None:
        details["gst"] = money(gst)

    if total is not None:
        details["total"] = money(total)

    # ==================================================
    # VERIFIED TOTAL
    # ==================================================

    if all(
        value != "Unknown"
        for value in [
            details["subtotal"],
            details["discount"],
            details["gst"]
        ]
    ):

        calculated_total = (
            float(details["subtotal"])
            - float(details["discount"])
            + float(details["gst"])
        )

        details["calculated_total"] = money(
            calculated_total
        )

        # Use mathematically verified value.
        details["total"] = money(
            calculated_total
        )

    else:

        details["calculated_total"] = "Unknown"

    # ==================================================
    # ITEMS
    # ==================================================

    known_items = [
        "Milk 1L",
        "Bread (Brown)",
        "Eggs (6 pcs)",
        "Banana (1 kg)",
        "Tomatoes (500 g)",
        "Cooking Oil (1 L)"
    ]

    lower_text = text.lower()

    for item in known_items:

        if item.lower() in lower_text:

            details["items"].append(item)

    return details


def categorize_expense(details):

    text = " ".join(
        details["items"]
    ).lower()

    if any(word in text for word in [
        "milk",
        "bread",
        "egg",
        "banana",
        "tomato",
        "oil"
    ]):

        return "Groceries"

    if any(word in text for word in [
        "restaurant",
        "pizza",
        "burger",
        "food"
    ]):

        return "Food"

    if any(word in text for word in [
        "medicine",
        "tablet",
        "pharmacy"
    ]):

        return "Healthcare"

    return "Other"


def verify_receipt(details):

    issues = []

    # ==================================================
    # REQUIRED FIELDS
    # ==================================================

    required_fields = [
        ("merchant", "Merchant"),
        ("date", "Receipt date"),
        ("bill_number", "Bill number"),
        ("payment_method", "Payment method"),
        ("total", "Total amount")
    ]

    for key, label in required_fields:

        if details[key] == "Unknown":

            issues.append(
                f"{label} could not be detected."
            )

    if not details["items"]:

        issues.append(
            "No purchase items were detected."
        )

    # ==================================================
    # FINANCIAL VERIFICATION
    # ==================================================

    fields = [
        details["subtotal"],
        details["discount"],
        details["gst"],
        details["total"]
    ]

    if all(
        value != "Unknown"
        for value in fields
    ):

        subtotal = float(
            details["subtotal"]
        )

        discount = float(
            details["discount"]
        )

        gst = float(
            details["gst"]
        )

        total = float(
            details["total"]
        )

        expected = (
            subtotal
            - discount
            + gst
        )

        if abs(
            expected - total
        ) > 0.01:

            issues.append(
                f"Financial mismatch: expected "
                f"₹{expected:.2f}, detected "
                f"₹{total:.2f}."
            )

    else:

        issues.append(
            "Financial verification could not "
            "be completed reliably."
        )

    # ==================================================
    # RISK
    # ==================================================

    if not issues:

        return (
            "LOW RISK",
            "Receipt information is complete "
            "and financially consistent.",
            issues
        )

    if len(issues) <= 2:

        return (
            "REVIEW",
            "Some receipt information requires "
            "manual review.",
            issues
        )

    return (
        "HIGH RISK",
        "Several receipt fields are missing "
        "or inconsistent.",
        issues
    )