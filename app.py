import os
import json
import hashlib
from datetime import datetime

import streamlit as st
from PIL import Image

from receipt_analyzer import (
    analyze_receipt,
    extract_receipt_details,
    categorize_expense,
    verify_receipt
)


# =========================================================
# CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="AgentReceipt",
    page_icon="🧾",
    layout="wide"
)

HISTORY_FILE = "receipt_history.json"


# =========================================================
# HISTORY FUNCTIONS
# =========================================================

def load_history():

    if not os.path.exists(HISTORY_FILE):
        return []

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return []


def save_history(history):

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            history,
            file,
            indent=2
        )


# =========================================================
# RECEIPT ID
# =========================================================

def create_receipt_id(details):

    values = [
        details.get("merchant", ""),
        details.get("date", ""),
        details.get("bill_number", ""),
        details.get("total", ""),
        details.get("transaction_id", "")
    ]

    raw = "|".join(
        str(value)
        for value in values
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def is_duplicate(receipt_id, history):

    return any(
        item.get("receipt_id") == receipt_id
        for item in history
    )


# =========================================================
# HEADER
# =========================================================

st.title("🧾 AgentReceipt")

st.subheader(
    "Receipt Accountability Agent"
)

st.write(
    "Extract → Verify → Explain → Detect Duplicates"
)

st.caption(
    "Local receipt analysis with transparent verification."
)

st.divider()


# =========================================================
# LOAD HISTORY
# =========================================================

history = load_history()


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title("AgentReceipt")

st.sidebar.metric(
    "Receipts Analyzed",
    len(history)
)

st.sidebar.info(
    "🔒 Receipt processing is performed locally."
)


# =========================================================
# TABS
# =========================================================

analyze_tab, history_tab = st.tabs(
    [
        "🔍 Analyze Receipt",
        "📚 Receipt History"
    ]
)


# =========================================================
# ANALYZE TAB
# =========================================================

with analyze_tab:

    uploaded_file = st.file_uploader(
        "Upload a receipt",
        type=[
            "jpg",
            "jpeg",
            "png"
        ]
    )

    if uploaded_file:

        image = Image.open(
            uploaded_file
        )

        st.image(
            image,
            caption="Uploaded Receipt",
            width=500
        )

        if st.button(
            "🔍 Analyze Receipt",
            type="primary",
            use_container_width=True
        ):

            with st.spinner(
                "Analyzing receipt..."
            ):

                # OCR
                ocr_text = analyze_receipt(
                    image
                )

                # Extraction
                details = extract_receipt_details(
                    ocr_text
                )

                # Category
                category = categorize_expense(
                    details
                )

                # Verification
                risk, explanation, issues = (
                    verify_receipt(details)
                )

                # Receipt fingerprint
                receipt_id = create_receipt_id(
                    details
                )

                duplicate = is_duplicate(
                    receipt_id,
                    history
                )

            # =================================================
            # DUPLICATE RESULT
            # =================================================

            if duplicate:

                st.error(
                    "🚨 POSSIBLE DUPLICATE RECEIPT"
                )

            else:

                st.success(
                    "✅ New receipt detected"
                )

            st.divider()

            # =================================================
            # SUMMARY
            # =================================================

            st.subheader(
                "📊 Receipt Summary"
            )

            col1, col2, col3 = st.columns(3)

            # -------------------------------------------------
            # COLUMN 1
            # -------------------------------------------------

            with col1:

                st.metric(
                    "Merchant",
                    details["merchant"]
                )

                # IMPORTANT:
                # Never present an unreliable amount
                # as a verified amount.

                if risk == "LOW RISK":

                    st.metric(
                        "Verified Total",
                        f"₹{details['total']}"
                    )

                else:

                    st.metric(
                        "Verified Total",
                        "Needs Review"
                    )

                st.write(
                    f"**Date:** "
                    f"{details['date']}"
                )

            # -------------------------------------------------
            # COLUMN 2
            # -------------------------------------------------

            with col2:

                st.write(
                    f"**Bill Number:** "
                    f"{details['bill_number']}"
                )

                st.write(
                    f"**Payment:** "
                    f"{details['payment_method']}"
                )

                st.write(
                    f"**Transaction ID:** "
                    f"{details['transaction_id']}"
                )

            # -------------------------------------------------
            # COLUMN 3
            # -------------------------------------------------

            with col3:

                st.write(
                    f"**Category:** "
                    f"{category}"
                )

                # Don't present uncertain financial
                # fields as verified either.

                if risk == "LOW RISK":

                    st.write(
                        f"**Subtotal:** "
                        f"₹{details['subtotal']}"
                    )

                    st.write(
                        f"**GST:** "
                        f"₹{details['gst']}"
                    )

                else:

                    st.write(
                        "**Subtotal:** Needs Review"
                    )

                    st.write(
                        "**GST:** Needs Review"
                    )

            # =================================================
            # VERIFICATION
            # =================================================

            st.divider()

            st.subheader(
                "🛡️ Receipt Verification"
            )

            if risk == "LOW RISK":

                st.success(
                    "✅ LOW RISK"
                )

            elif risk == "REVIEW":

                st.warning(
                    "⚠️ REVIEW REQUIRED"
                )

            else:

                st.error(
                    "🚨 HIGH RISK"
                )

            st.write(
                explanation
            )

            # =================================================
            # ISSUES
            # =================================================

            if issues:

                st.write(
                    "**Why?**"
                )

                for issue in issues:

                    st.write(
                        f"• {issue}"
                    )

            # =================================================
            # ITEMS
            # =================================================

            st.divider()

            st.subheader(
                "🛒 Detected Items"
            )

            if details["items"]:

                for item in details["items"]:

                    st.write(
                        f"• {item}"
                    )

            else:

                st.write(
                    "No items detected."
                )

            # =================================================
            # SAVE TO HISTORY
            # =================================================

            # Save the analysis even when REVIEW is required,
            # because the history is useful for auditability.
            # The stored risk status makes it clear that
            # the receipt was not approved.

            if not duplicate:

                history.append(
                    {
                        "receipt_id":
                            receipt_id,

                        "merchant":
                            details["merchant"],

                        "date":
                            details["date"],

                        "bill_number":
                            details["bill_number"],

                        "total":
                            details["total"],

                        "category":
                            category,

                        "risk":
                            risk,

                        "analyzed_at":
                            datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                    }
                )

                save_history(
                    history
                )

                st.success(
                    "💾 Receipt saved to local history."
                )

            # =================================================
            # RAW OCR
            # =================================================

            with st.expander(
                "📄 View Raw OCR Text"
            ):

                st.text(
                    ocr_text
                )


# =========================================================
# HISTORY TAB
# =========================================================

with history_tab:

    st.subheader(
        "📚 Local Receipt History"
    )

    history = load_history()

    if not history:

        st.info(
            "No receipts analyzed yet."
        )

    else:

        for receipt in reversed(
            history
        ):

            with st.expander(
                f"{receipt['merchant']} "
                f"— ₹{receipt['total']} "
                f"— {receipt['date']}"
            ):

                st.write(
                    f"**Bill:** "
                    f"{receipt['bill_number']}"
                )

                st.write(
                    f"**Category:** "
                    f"{receipt['category']}"
                )

                st.write(
                    f"**Risk:** "
                    f"{receipt['risk']}"
                )

                st.caption(
                    f"Analyzed: "
                    f"{receipt['analyzed_at']}"
                )