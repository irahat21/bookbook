"""Business-rule constants (SRS Table 2, R1-R15).

Every threshold used by the services lives here, tagged with its rule number,
so a rule can never drift between two code paths (SRS Section 6.1).
"""

# Roles and statuses (Section 3.1 data dictionary)
VISITOR, RC, VC, SU = "VS", "RC", "VC", "SU"
CUSTOMER_ROLES = (RC, VC)
ACTIVE, SUSPENDED = "ACTIVE", "SUSPENDED"

# R2 - biometric match thresholds and lockout
FACE_THRESHOLD = 0.60
VOICE_THRESHOLD = 0.75
MAX_LOGIN_FAILS = 3
LOCK_MINUTES = 5
MIN_VOICE_SECONDS = 2.0

# R3 - popularity = browse_count + 3 x purchase_count, top 3 on Home
POPULAR_PURCHASE_WEIGHT = 3
HOME_BOOK_COUNT = 3

# R4 - personalized profile weights: a purchase counts 3, a view 1
PROFILE_W_BUY = 3
PROFILE_W_VIEW = 1

# R5 - VIP promotion: purchases > 3 OR spending > $200 since joining / last demotion
PROMO_PURCHASES = 3
PROMO_SPENT = 200.00

# R6 - VIP pays 90% of list price
VIP_RATE = 0.10

# R7 - fine for a purchase attempt with insufficient funds
FINE_AMOUNT = 1.00

# UC-07 E1 - largest single deposit
MAX_DEPOSIT = 10000.00

# R9 - taboo words: 1..3 masked, more than 3 blocked
TABOO_BLOCK_ABOVE = 3

# R10 - an RC with more than 2 warnings is suspended
RC_SUSPEND_ABOVE = 2

# R12 - weighted rating
W_VERIFIED = 2.0
W_OTHER = 1.0

# R13 - order lists need more than 3 ratings
MIN_RATINGS = 3
NO_ORDER_BELOW = 2.0
TO_ORDER_ABOVE = 4.0
LIST_NONE, LIST_NO_ORDER, LIST_TO_ORDER = "NONE", "NO_ORDER", "TO_ORDER"

# R14 - chatbot access: which question intents each role may ask (SRS 4.20 PERMITTED)
STORE, ACCOUNT, GENERAL, ADMIN = "STORE", "ACCOUNT", "GENERAL", "ADMIN"
CHAT_PERMITTED = {
    VISITOR: {STORE},
    RC: {STORE, ACCOUNT, GENERAL},
    VC: {STORE, ACCOUNT, GENERAL},
    SU: {STORE, ACCOUNT, GENERAL, ADMIN},
}

# R15 - Reading Companion: chapters readable without owning the book
FREE_CHAPTERS = 1

# UC-01 step 4 - registration validation
USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,20}$"
EMAIL_PATTERN = r"^[^@ ]+@[^@ ]+\.[^@ ]+$"
MAX_FACE_RETRIES = 3          # UC-01 E3

# UC-04 - catalog paging
PAGE_SIZE = 12

# UC-04 step 4 / E4 - cover search: top 5 covers; best similarity below 0.25 = no match
# (SRS value for OpenCLIP; the MOCK embedder has its own measured threshold, A-33)
COVER_TOP_K = 5
COVER_MIN_SIM = 0.25

# UC-10 - review length
REVIEW_MAX_CHARS = 1000

# Transaction types (SRS 3.1 TRANSACTION.type) and review statuses (REVIEW.status)
DEPOSIT, PURCHASE, FINE = "DEPOSIT", "PURCHASE", "FINE"
PUBLISHED, BLOCKED = "PUBLISHED", "BLOCKED"

# R10 consequences returned by WarningService.issue (SRS 4.16)
DEMOTED = "DEMOTED"
