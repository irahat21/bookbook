# BookOrbit AI – Phase II Design Report (text extract)

> Plain-text extract of `docs/BookOrbit_AI_Phase2_Design_Report.pdf` (v2.0), made with `pypdf` so later sessions can grep it without PDF tools. The PDF stays the source of truth: diagrams (figures, Petri nets, E-R, mockups) are not included, and tables are flattened to one row per line. `<!-- page N -->` marks PDF page breaks.

<!-- page 1 -->
Borbit LLC.
BookOrbit AI
Phase II: Design Report
AI-Enabled Multimodal Smart Bookstore
Version 2.0
CSC 322 - Software Engineering
Zakiah Almontaser, Yixin Chen, Evan Florentino, Ibrahim Rahat, Selina Zhu

<!-- page 2 -->
Revision History
Date Version Description Author
21/Oct/26 1.0 Phase I: Software Requirements Specification Zakiah Almontaser, Yixin Chen, Evan Florentino, Ibrahim Rahat, Selina Zhu
24/Nov/26 2.0
Phase II: Design Report - all 18 use cases,
Petri nets, E-R diagram, pseudo-code for
every method, screens and prototype
Zakiah Almontaser, Yixin Chen,
Evan Florentino, Ibrahim Rahat,
Selina Zhu

<!-- page 3 -->
Table of Contents

<!-- page 4 -->

# 1. Introduction

BookOrbit AI is a local, AI-enabled multimodal bookstore. Visitors browse and search the catalog;
Registered Customers (RC) and VIP Customers (VC) sign in with a face or voice sample, keep a
cash balance, buy books, write moderated reviews and receive personalized recommendations;
Super-Users (SU) maintain the catalog, the taboo word list and suspended accounts. A local LLM
served by Ollama powers the chatbot (with Retrieval-Augmented Generation over store data) and
our creative feature, the Smart Reading Companion.
This Phase II report turns the Phase I specification into a design the team can implement directly. It
defines the classes, the data that each class reads and writes, and the logic of every method. Three
changes respond to the Phase I review:
- All 18 use cases are now specified individually. The Phase I report described 8 grouped
use cases while the use-case diagram showed 18. Section 2 gives every use case in the
diagram its own normal and exceptional scenarios and its own diagram.
- Inconsistent rules were resolved. Phase I gave two different VIP demotion rules (Section 1.3
vs. Section 3). The team decided that a VIP is demoted after one blocked comment. Section
1.2 lists every business rule in its final form.
- The Phase I flowcharts were reused in the detailed design (Section 4), as the reviewer
suggested.

## 1.1 Architecture and Technology

The application is one Python program with four layers. Only the persistence layer touches the disk,
so the flat-file storage required by the specification is isolated behind one class (FileStore).
*Table 1: System layers and technology*
Layer Responsibility Technology
Presentation
Tkinter windows and screens; reads the Session to
decide which sidebar items and buttons each role
sees
Python 3.12, Tkinter / ttk
Control / service
Business rules: authentication, catalog,
purchasing, wallet, reviews, warnings, status
changes, ratings, administration, chatbot, Reading
Companion
Plain Python classes
AI components
Face detection and matching, voice matching,
cover-image search, taboo moderation, retrieval,
text generation
Ultralytics YOLOv8-face (detect),
FaceNet embeddings, Resemblyzer
(voice), OpenCLIP ViT-B/32 (covers),
Ollama llama3.2:3b + nomic-
embed-text
Persistence Read / append / rewrite records in text files; generate IDs JSON Lines .txt files in data/; atomic rewrite with a temp file + os.replace
All models run locally and are free, as required: Ollama serves the LLM and the text-embedding
model on localhost:11434; book texts come from Project Gutenberg. Each table is a text file
holding one JSON object per line (for example data/users.txt); embeddings are stored as .npy
files referenced by path.

<!-- page 5 -->

## 1.2 Business Rules (final)

The rules below are the single source of truth for the use cases (Section 2) and the pseudo-code
(Section 4).
*Table 2: Business rules used throughout the design*
\# Rule Design decision
R1 Who signs in RC, VC and SU sign in with a face sample (primary) or a voice sample (alternate). Visitors never sign in.
R2 Biometric match Cosine similarity between the live and stored embedding: face >= 0.60, voice >= 0.75. Three consecutive failures lock the username for 5 minutes.
R3 Popular books Popularity = browse_count + 3 x purchase_count. The top 3 are shown to Visitors and Super-Users; ties are broken by weighted average, then title.
R4 Personalized books
RC and VC get the top 3 unowned books by profile score (category, author and
keyword matches; purchases weigh 3, views weigh 1). With no history, popular books
are shown.
R5 VIP promotion An RC whose purchases since joining or since the last demotion are > 3, or whose spending in that period is > $200, becomes VC right after that purchase.
R6 VIP discount VC pays 90% of the list price, rounded to the cent. The discount starts with the first purchase after promotion.
R7 Insufficient funds The purchase is rejected and a $1.00 fine is charged. If the balance then drops below $0 the account is SUSPENDED.
R8 Suspended accounts A suspended user can sign in only to the wallet (deposit, view ledger). An SU can reopen the account only when the balance is >= $0; reopening resets warnings to 0.
R9 Taboo words
Case-insensitive whole-word match. A comment with 1 to 3 taboo words is published
with each word replaced by asterisks of the same length. A comment with more than
3 is blocked and the author gets 1 warning.
R10 Warnings RC: more than 2 warnings (i.e., the 3rd) suspends the account. VC: any blocked comment demotes the user to RC and resets the promotion counters.
R11 Who reviews RC and VC write reviews (the use-case diagram links Submit Book Reviews to customers), because warnings need an account.
R12 Weighted rating Verified buyers' ratings have weight 2.0, others 1.0. Average = sum(rating x weight) / sum(weight), over published reviews.
R13 Order lists After each published review: more than 3 ratings and average < 2 -> No-Order List; more than 3 ratings and average > 4 -> To-Order List; otherwise unlisted.
R14 Chatbot access Visitor: store questions only. RC/VC: store questions, their own account, general questions. SU: all of that plus administrative data.
R15 Reading Companion RC and VC, on books with a public-domain text. Owned books are fully readable; for other books only the first chapter is available.

## 1.3 Collaboration Class Diagram

Figure 1 gives the overall picture. Each box is a class with its key operations; each arrow is a
collaboration, numbered in the order a typical session uses it. Table 3 explains the numbers. Every

<!-- page 6 -->
control class also reads and writes through FileStore (message 14), which is drawn as one arrow
to keep the figure readable.

<!-- page 7 -->
*Figure 1: Collaboration class diagram of BookOrbit AI (layers: presentation, control, AI components, persistence)*

<!-- page 8 -->
*Table 3: Collaborations shown in Figure 1*
Msg From -> To Meaning
1 MainWindow -> Screens Show the screen for the current role (sidebar built from the Session role).
2 Screens -> Session Read the signed-in user and role; guard role-only actions.
3, 3.1 Screens -> AuthService -> BiometricEngine Register (enroll face/voice) and log in (verify sample).
4, 4.1 Screens -> CatalogService -> CoverIndex Browse, text search, cover-image search, book details.
5 Screens -> RecommendationEngine Top-3 popular or personalized books for the home page.
6, 6.1-6.3 Screens -> PurchaseService -> WalletService / StatusManager Buy a book: price with VIP discount, debit or fine, VIP promotion, suspension on negative balance.
7, 7.1-7.4
Screens -> ReviewService ->
ModerationEngine / WarningService /
RatingService
Moderate a review, warn / demote / suspend, recalculate
weighted rating and order lists.
7.1.1 ModerationEngine -> TabooService Load the current taboo list.
8, 8.1, 8.2 Screens -> ChatbotService -> RAGRetriever / LLMClient Answer a question within the role's permission scope.
9, 9.1, 9.2 Screens -> ReadingCompanion -> RAGRetriever / LLMClient Summaries, explanations, definitions and quizzes on a book.
10, 10.1-
10.3
Screens -> AdminService ->
StatusManager / CoverIndex /
RAGRetriever
Add a book (index cover and text) and reopen suspended
accounts.
11 Screens -> TabooService SU adds, edits or deletes taboo words.
12 Screens -> WalletService Deposit money; view the ledger.
13 Screens -> RatingService SU views the No-Order and To-Order lists.
14, 15 All services -> FileStore -> text files Load, append, update and rewrite JSON Lines records.

<!-- page 9 -->

# 2. Use Cases

Table 4 lists the 18 use cases of the Phase I use-case diagram. Each one below has its actors, pre-
and post-conditions, a normal scenario, its exceptional scenarios and a diagram. Four use cases
with several decision points are modelled as Petri nets (UC-02, UC-08, UC-10, UC-12); the other
fourteen use sequence diagrams.
Petri net notation: circles are places (states), filled bars are transitions (events), a dot is a token. A
transition fires when every input place holds a token (or the number on the arc). A dashed arc
ending in a small circle is an inhibitor arc: the transition can fire only when that place is empty. The
places are explained in a table under each net.
*Table 4: Use cases and diagram types*
ID Use case Actors Diagram
UC-01 Register an Account Visitor Sequence
UC-02 Log In Using Biometric Authentication Registered Customer, VIP Customer, Super- User Petri net
UC-03 View Popular Books Visitor, Super-User Sequence
UC-04 Browse and Search Books Visitor, Registered Customer, VIP Customer, Super-User Sequence
UC-05 View Book Details and Reviews Visitor, Registered Customer, VIP Customer, Super-User Sequence
UC-06 Receive Personalized Recommendations Registered Customer, VIP Customer Sequence
UC-07 Manage Cash Balance and Ledger Registered Customer, VIP Customer (also when suspended) Sequence
UC-08 Purchase Books Registered Customer, VIP Customer Petri net
UC-09 Receive VIP Discount VIP Customer (extends UC-08) Sequence
UC-10 Submit Book Reviews Registered Customer, VIP Customer Petri net
UC-11 Receive Review Warnings Registered Customer, VIP Customer (extends UC-10) Sequence
UC-12 Interact with AI Chatbot Visitor, Registered Customer, VIP Customer, Super-User Petri net
UC-13 Access Additional Chatbot Information Super-User (extends UC-12) Sequence
UC-14 Use Smart Reading Companion Registered Customer, VIP Customer Sequence
UC-15 Add New Books Super-User Sequence
UC-16 Manage Taboo Word List Super-User Sequence
UC-17 Reopen Suspended Accounts Super-User Sequence
UC-18 View Book Classification Lists Super-User Sequence

<!-- page 10 -->

## 2.1 UC-01: Register an Account

Item Description
Actors Visitor; Biometric Authentication Component
Summary A Visitor creates a Registered Customer account and enrolls a face sample (and optionally a voice sample) for future sign-in.
Preconditions Application running; user not signed in; camera available.
Postconditions A new RC account (status ACTIVE, balance $0.00, 0 warnings) and its biometric template(s) are stored.
Normal scenario
1. Visitor clicks Register on the sidebar.
2. System shows the form (full name, username, email), a live camera preview and an optional 3-
second voice recording.
3. Visitor fills in the form and clicks Capture Face (and optionally Record Voice).
4. System validates the form: username 3-20 characters (letters, digits, underscore) and not
already used; email contains a single @ and a domain.
5. BiometricEngine detects exactly one face with YOLO, crops it, computes the embedding and
saves it to data/biometrics/<uid>_face.npy.
6. System appends the user to users.txt (role RC, status ACTIVE) and the template to
biometrics.txt.
7. System shows "Account created - please sign in" and opens the Sign In screen.
Exceptional scenarios
- E1 Username taken: "This username is already in use"; the form keeps its values.
- E2 Invalid field: each invalid field is outlined in red with a short reason; nothing is saved.
- E3 No face / several faces in the frame: "Make sure only your face is visible"; the user
retakes the photo (up to 3 tries, then the registration is cancelled).
- E4 No camera: the user may enroll with voice only; with neither camera nor microphone the
account cannot be created.
- E5 Write error: the template file is deleted again so no half-created account remains; an error
is shown.

<!-- page 11 -->
*Figure 2: UC-01 Register an Account - sequence diagram*

<!-- page 12 -->

## 2.2 UC-02: Log In Using Biometric Authentication

Item Description
Actors Registered Customer, VIP Customer, Super-User; Biometric Authentication Component
Summary A registered user proves their identity with a face or voice sample and receives the dashboard for their role.
Preconditions The user has an account and an enrolled template; the username is not locked.
Postconditions A Session holds the user and role; the role's dashboard is shown (wallet-only if suspended).
Normal scenario
1. User clicks Sign In and types the username.
2. System checks that the username exists and is not locked.
3. User selects Face (default) or Voice and captures a sample.
4. BiometricEngine computes the live embedding and compares it with the stored one (R2).
5. The score meets the threshold: the attempt is logged as successful and the Session starts.
6. The account is ACTIVE: RC/VC see the customer home with recommendations; SU sees the
admin home.
Exceptional scenarios
- E1 Unknown username: "No account with that username"; no attempt is counted.
- E2 Sample does not match: "Not recognised - try again (attempt n of 3)"; the failure is
logged.
- E3 Third consecutive failure: the username is locked for 5 minutes (Petri net transition T7,
which needs 3 tokens in P5).
- E4 Account suspended: the user enters wallet-only mode with a banner explaining how to
get reactivated (R8).
- E5 No face detected / audio too short: the user is asked to recapture; this is not counted as
a failure.
- E6 Template file missing or corrupt: the user is told to use the other method or contact a
Super-User.

<!-- page 13 -->
*Figure 3: UC-02 Log In Using Biometric Authentication - Petri net*
*Table 5: Places of the UC-02 Petri net*
Place Meaning Place Meaning
P1 Login screen open P6 Account locked 5 min
P2 Username entered P7 Identity verified
P3 Awaiting sample P8 Full dashboard
P4 Sample captured P9 Wallet-only mode
P5 Failed attempts P10 'Unknown user' shown

<!-- page 14 -->

## 2.3 UC-03: View Popular Books

Item Description
Actors Visitor, Super-User; AI Recommendation Component
Summary The home page shows the three most browsed and purchased books.
Preconditions Application running; the user is a Visitor or a signed-in Super-User.
Postconditions Up to three book cards are displayed.
Normal scenario
1. User opens the home page.
2. HomeScreen asks RecommendationEngine for the home books of the current session.
3. Because the role is VS or SU, the engine calls top_popular(3).
4. The engine loads all books, computes popularity (R3), sorts and returns the top three.
5. HomeScreen shows the cards (cover, title, author, weighted rating); clicking a card opens UC-
05.
Exceptional scenarios
- E1 Fewer than three books: all available books are shown.
- E2 Empty catalog: "No books available yet".
- E3 Ties: broken by weighted average, then title, so the order is stable.

<!-- page 15 -->
*Figure 4: UC-03 View Popular Books - sequence diagram*

<!-- page 16 -->

## 2.4 UC-04: Browse and Search Books

Item Description
Actors Visitor, Registered Customer, VIP Customer, Super-User
Summary Users find books by category, author, keyword, publication year or by uploading a photo of a cover.
Preconditions The book catalog exists.
Postconditions A list of matching books is shown, best matches first.
Normal scenario
1. User opens Browse.
2. User picks a category, or types a query and chooses the field (title, author, keyword, year
range), or clicks the camera icon and selects a cover image.
3. For text: CatalogService filters the books and ranks exact title matches first, then partial
matches.
4. For an image: CatalogService asks CoverIndex for the 5 covers most similar to the uploaded
image.
5. The results are shown 12 per page; selecting one opens UC-05.
Exceptional scenarios
- E1 No match: "No books found" with a Clear filters button.
- E2 Invalid year range (from > to, or non-numeric): the field is highlighted.
- E3 Unreadable or non-image file: "Please choose a JPG or PNG image".
- E4 Best cover similarity < 0.25: treated as no match.
- E5 Image model not loaded: cover search is disabled with a tooltip; text search still works.

<!-- page 17 -->
*Figure 5: UC-04 Browse and Search Books - sequence diagram*

<!-- page 18 -->

## 2.5 UC-05: View Book Details and Reviews

Item Description
Actors Visitor, Registered Customer, VIP Customer, Super-User
Summary Shows a book's information, weighted rating and published reviews, and records the view for popularity and recommendations.
Preconditions The user selected a book card.
Postconditions Details are displayed; browse_count is incremented; a browse event is stored for signed-in customers.
Normal scenario
1. User clicks a book.
2. CatalogService loads the book.
3. The book's browse_count is incremented; for RC/VC a BROWSE_EVENT is appended.
4. ReviewService returns the published reviews (masked text, verified-buyer badge), newest first.
5. The screen shows title, author, category, year, description, price (VIP price for VC), weighted
rating and reviews, plus role-based buttons: Buy, Write Review, Reading Companion (RC/VC).
Exceptional scenarios
- E1 Book no longer exists: "Book unavailable" and return to the catalog.
- E2 No reviews: "No reviews yet".
- E3 Suspended user: Buy and Write Review are disabled with a tooltip.

<!-- page 19 -->
*Figure 6: UC-05 View Book Details and Reviews - sequence diagram*

<!-- page 20 -->

## 2.6 UC-06: Receive Personalized Recommendations

Item Description
Actors Registered Customer, VIP Customer; AI Recommendation Component
Summary Signed-in customers see three recommended books based on their browsing and purchasing history.
Preconditions An RC or VC is signed in.
Postconditions Three recommended (or fallback popular) books are shown.
Normal scenario
1. Customer signs in or returns to Home.
2. RecommendationEngine loads the customer's browse events and purchases.
3. It builds a profile: weights for categories, authors and keywords (purchase = 3, view = 1).
4. It scores every book the customer does not own and keeps the top three (R4).
5. Home shows them under Recommended for You.
Exceptional scenarios
- E1 No history yet: popular books are shown under Popular right now.
- E2 Fewer than three unowned scored books: the list is filled with popular books.
- E3 The customer owns every book: popular books are shown.

<!-- page 21 -->
*Figure 7: UC-06 Receive Personalized Recommendations - sequence diagram*

<!-- page 22 -->

## 2.7 UC-07: Manage Cash Balance and Ledger

Item Description
Actors Registered Customer, VIP Customer (also when suspended)
Summary Customers deposit money and review every deposit, purchase and fine.
Preconditions A customer is signed in (full or wallet-only mode).
Postconditions The balance and ledger reflect the deposit.
Normal scenario
1. Customer opens My Balance; the balance and ledger (newest first) are shown.
2. Customer types an amount and clicks Add Funds.
3. WalletService validates the amount.
4. It appends a DEPOSIT transaction with the new balance_after and updates the user's balance.
5. The screen refreshes. If the account is suspended and the balance is now >= $0, a note says
a Super-User can now reactivate the account.
Exceptional scenarios
- E1 Invalid amount: <= 0, not a number, more than 2 decimals, or more than $10,000 in one
deposit: "Enter a valid amount".
- E2 Write error: no change is made and an error is shown.

<!-- page 23 -->
*Figure 8: UC-07 Manage Cash Balance and Ledger - sequence diagram*

<!-- page 24 -->

## 2.8 UC-08: Purchase Books

Item Description
Actors Registered Customer, VIP Customer
Summary A customer buys a book with the account balance; the system applies the discount, fines, promotion and suspension rules.
Preconditions An ACTIVE customer is signed in and viewing a book they do not own.
Postconditions Either the purchase is recorded, or the purchase is rejected with a fine (and possibly a suspension).
Normal scenario
1. Customer clicks Buy Now.
2. PurchaseService computes the final price (UC-09 for VC) and shows a confirmation dialog.
3. Customer confirms.
4. The balance covers the price: a PURCHASE transaction and a PURCHASE record are written;
the balance, purchase_count, total_spent and promotion counters are updated; the book's
purchase_count is incremented.
5. StatusManager evaluates promotion (R5); if met, the RC becomes VC and is told so.
6. A receipt is shown; the book is now fully available in the Reading Companion.
Exceptional scenarios
- E1 Insufficient funds: the purchase is rejected, a $1.00 FINE transaction is posted (R7).
- E2 Balance negative after the fine: the account is SUSPENDED and the user is switched to
wallet-only mode.
- E3 Already owned: "You already own this book".
- E4 Suspended account: the Buy button is disabled.
- E5 Customer cancels the dialog: nothing changes.

<!-- page 25 -->
*Figure 9: UC-08 Purchase Books - Petri net*
*Table 6: Places of the UC-08 Petri net*
Place Meaning Place Meaning
P1 Book selected P6 VIP Customer
P2 Price computed P7 Remains RC / already VC
P3 Balance P8 Fine charged ($1)
P4 Paid P9 Rejected, account active
P5 Purchase recorded P10 Account suspended

<!-- page 26 -->

## 2.9 UC-09: Receive VIP Discount

Item Description
Actors VIP Customer (extends UC-08)
Summary During a purchase, a VIP pays 10% less than the list price.
Preconditions UC-08 is in progress and the buyer is a VC.
Postconditions The purchase record stores list price, discount and price paid.
Normal scenario
1. PurchaseService re-reads the user from users.txt (the role may have changed since sign-
in).
2. Role is VC: discount = round(price x 0.10, 2).
3. The confirmation dialog and receipt show list price, VIP discount and amount paid.
4. The ledger entry is labelled "VIP -10%".
Exceptional scenarios
- E1 Demoted after the page was opened: no discount; the dialog shows the updated price
before the customer confirms.
- E2 Promoted by this purchase: the discount starts with the next purchase (R6).

<!-- page 27 -->
*Figure 10: UC-09 Receive VIP Discount - sequence diagram*

<!-- page 28 -->

## 2.10 UC-10: Submit Book Reviews

Item Description
Actors Registered Customer, VIP Customer
Summary A customer rates a book (1-5 stars) and writes a comment that is moderated before it is published.
Preconditions An ACTIVE customer is on a book's page.
Postconditions The review is published (masked if needed) and the book's rating and list status are updated, or the review is blocked and UC-11 runs.
Normal scenario
1. Customer selects 1-5 stars, types a comment and clicks Submit Review.
2. ReviewService validates the rating and the length (1-1000 characters).
3. ModerationEngine counts taboo words (R9).
4. Three or fewer: taboo words are masked and the review is stored as PUBLISHED with weight
2.0 if the author bought the book, else 1.0.
5. RatingService recalculates the weighted average and rating count (R12).
6. RatingService classifies the book into No-Order, To-Order or unlisted (R13).
7. The screen shows "Review published" (and how many words were masked).
Exceptional scenarios
- E1 No star selected / empty or too long comment: an error message; nothing is stored.
- E2 More than 3 taboo words: the review is stored as BLOCKED (never shown) and UC-11
issues a warning.
- E3 Suspended account: the form is disabled.
*Figure 11: UC-10 Submit Book Reviews - Petri net*

<!-- page 29 -->
*Table 7: Places of the UC-10 Petri net*
Place Meaning Place Meaning
P1 Review entered P7 Suspended
P2 Moderated P8 Active, warned
P3 Published (masked) P9 Rating updated
P4 Blocked P10 No-Order List
P5 Warning recorded P11 To-Order List
P6 Demoted to RC P12 Unlisted

<!-- page 30 -->

## 2.11 UC-11: Receive Review Warnings

Item Description
Actors Registered Customer, VIP Customer (extends UC-10)
Summary When a comment is blocked, the author receives a warning and the status rules are applied.
Preconditions UC-10 blocked a comment.
Postconditions A WARNING record exists; the user may be demoted or suspended; a STATUS_CHANGE is logged when the status changes.
Normal scenario
1. WarningService appends a warning linked to the blocked review and increments the user's
warning count.
2. It applies R10: a VC is demoted to RC; an RC with more than 2 warnings is suspended.
3. The user sees a message with the warning number and any status change; warnings are listed
under My Reviews.
Exceptional scenarios
- E1 VIP demoted: the price display drops the discount immediately; promotion counters restart
at 0.
- E2 RC suspended: the session switches to wallet-only mode.
- E3 RC with 1-2 warnings: no status change; the message says how many warnings remain
before suspension.

<!-- page 31 -->
*Figure 12: UC-11 Receive Review Warnings - sequence diagram*

<!-- page 32 -->

## 2.12 UC-12: Interact with AI Chatbot

Item Description
Actors Visitor, Registered Customer, VIP Customer, Super-User; AI Chatbot
Summary Users ask questions; the chatbot answers from store data (RAG) or with the local LLM, within the role's permissions (R14).
Preconditions The chat screen is open.
Postconditions An answer labelled with its source is shown and the exchange is logged.
Normal scenario
1. User types a question and clicks Send.
2. ChatbotService classifies the intent: STORE, ACCOUNT, GENERAL or ADMIN.
3. The intent is permitted for the role.
4. RAGRetriever searches the chunks allowed for the role (PUBLIC, plus the user's own account
facts for customers).
5. Relevant chunks found: the LLM answers using them; the answer is labelled [Store data].
6. No relevant chunk and the user is not a Visitor: the LLM answers directly, labelled [General
AI].
7. The question, answer and source are appended to chat_log.txt.
Exceptional scenarios
- E1 Intent not permitted (e.g., a Visitor asks about balances): "That information isn't available
for your account type".
- E2 Visitor asks a general question: "I can only answer questions about the store."
- E3 Ollama not running or no reply within 30 s: "The assistant is offline - please try again
later." (Petri net transition T4, enabled only when P12 'LLM ready' is empty).
- E4 Empty question: the Send button stays disabled.

<!-- page 33 -->
*Figure 13: UC-12 Interact with AI Chatbot - Petri net*
*Table 8: Places of the UC-12 Petri net*
Place Meaning Place Meaning
P1 Question entered P7 No store context
P2 Intent classified P8 Answer [Store data]
P3 Access denied P9 Answer [General AI]
P4 Authorized P10 'Store questions only'
P5 LLM error shown P11 Logged
P6 Context found P12 LLM ready

<!-- page 34 -->

<!-- page 35 -->

## 2.13 UC-13: Access Additional Chatbot Information

Item Description
Actors Super-User (extends UC-12)
Summary Super-Users ask the chatbot about administrative data: suspended accounts, warnings, balances, sales, order lists.
Preconditions An SU is signed in and using the chatbot.
Postconditions An answer labelled [Admin data] is shown and logged.
Normal scenario
1. SU asks, for example, "Which accounts are suspended?"
2. ChatbotService classifies the intent as ADMIN and confirms the role is SU.
3. admin_context() computes the facts directly from the files (counts, sums, lists).
4. The LLM phrases the answer using only those facts.
5. The answer is displayed and logged with source ADMIN.
Exceptional scenarios
- E1 Non-SU asks an admin question: treated as E1 of UC-12.
- E2 LLM offline: the computed facts are shown as a plain table.
- E3 Question not understood: the bot lists example admin questions.

<!-- page 36 -->
*Figure 14: UC-13 Access Additional Chatbot Information - sequence diagram*

<!-- page 37 -->

## 2.14 UC-14: Use Smart Reading Companion

Item Description
Actors Registered Customer, VIP Customer; AI Chatbot (LLM)
Summary
Our creative feature: an AI reading assistant that summarizes chapters, explains selected
passages, defines words in context and quizzes the reader, while remembering where they
stopped.
Preconditions A customer opens the companion from a book that has a public-domain text.
Postconditions The answer is shown and reading progress is saved.
Normal scenario
1. Customer clicks Reading Companion on the book page.
2. ReadingCompanion loads the chapter list and the saved chapter (R15).
3. Customer reads; selects text or a chapter and chooses Summarize, Explain selection,
Define word, Quiz me or types a question.
4. RAGRetriever fetches the relevant chunks of this book only.
5. The LLM generates the answer from those chunks; quizzes return 3 multiple-choice questions
with the correct answers hidden until the reader answers.
6. Progress (book, chapter, last action) is saved.
Exceptional scenarios
- E1 Book has no text: "The Reading Companion isn't available for this book".
- E2 Book not owned and chapter > 1: "Buy the book to keep reading" with a Buy button.
- E3 Explain with no selection: "Select a passage first".
- E4 LLM offline: the chapter text is still readable; AI buttons show an offline message.

<!-- page 38 -->
*Figure 15: UC-14 Use Smart Reading Companion - sequence diagram*

<!-- page 39 -->

## 2.15 UC-15: Add New Books

Item Description
Actors Super-User
Summary A Super-User adds a book to the catalog, with its cover and optional full text.
Preconditions An SU is on Manage Books.
Postconditions The book is in books.txt; its cover is in the cover index and its text in the RAG index.
Normal scenario
1. SU clicks Add New Book and fills title, author, category, keywords, year, price and
description; selects a cover image and optionally a Gutenberg .txt file.
2. AdminService validates the data.
3. The book is appended with counters at 0 and list status NONE.
4. CoverIndex embeds and stores the cover; RAGRetriever chunks and embeds the text.
5. The catalog table refreshes with the new book.
Exceptional scenarios
- E1 Missing required field or price <= 0: the fields are highlighted.
- E2 Same title and author already exists: "This book is already in the catalog".
- E3 Cover is not an image / text file not UTF-8: that file is rejected, the rest of the form stays.
- E4 Embedding model unavailable: the book is saved and flagged indexed=false; it is
indexed the next time the app starts.

<!-- page 40 -->
*Figure 16: UC-15 Add New Books - sequence diagram*

<!-- page 41 -->

## 2.16 UC-16: Manage Taboo Word List

Item Description
Actors Super-User
Summary A Super-User adds, edits or deletes the words used for review moderation.
Preconditions An SU is on Manage Taboo Words.
Postconditions taboo_words.txt is updated; new reviews use the new list.
Normal scenario
1. SU types a word and clicks Add (or Edit / Delete next to a word).
2. TabooService normalizes the word (trim, lower case).
3. The change is saved and logged as an ADMIN_ACTION.
4. The table refreshes.
Exceptional scenarios
- E1 Blank word, word with spaces, or duplicate: an error message, no change.
- E2 Deleting a word that is no longer present (two SUs at once): the list is reloaded.
- Note: changes apply to reviews submitted afterwards; published reviews are not re-scanned.

<!-- page 42 -->
*Figure 17: UC-16 Manage Taboo Word List - sequence diagram*

<!-- page 43 -->

## 2.17 UC-17: Reopen Suspended Accounts

Item Description
Actors Super-User
Summary A Super-User reactivates a suspended customer once the conditions are met.
Preconditions An SU is on User Management.
Postconditions The account is ACTIVE with 0 warnings; the action is logged.
Normal scenario
1. SU opens User Management; suspended users are listed with balance, warnings and
suspension reason.
2. SU clicks Reopen for a user.
3. StatusManager checks R8 (balance >= $0).
4. The user's status becomes ACTIVE and warnings reset to 0; a STATUS_CHANGE and an
ADMIN_ACTION are logged.
5. The list refreshes.
Exceptional scenarios
- E1 Balance still negative: "The customer must deposit at least $X first"; no change.
- E2 User is not suspended (already reopened by another SU): the list is reloaded.

<!-- page 44 -->
*Figure 18: UC-17 Reopen Suspended Accounts - sequence diagram*

<!-- page 45 -->

## 2.18 UC-18: View Book Classification Lists

Item Description
Actors Super-User
Summary A Super-User reviews the books the system put on the No-Order and To-Order lists.
Preconditions An SU is on Reports.
Postconditions Both lists are displayed.
Normal scenario
1. SU opens Reports > Classification Lists.
2. RatingService returns the books whose list_status is NO_ORDER and TO_ORDER.
3. Two tables show title, author, number of ratings and weighted average, sorted by average.
Exceptional scenarios
- E1 Both lists empty: "No books meet the thresholds yet".
- E2 A book's status is stale (e.g., file edited by hand): the SU can click Recalculate all, which
runs recalculate() on every book.

<!-- page 46 -->
*Figure 19: UC-18 View Book Classification Lists - sequence diagram*

<!-- page 47 -->

# 3. E-R Diagram

BookOrbit AI has 15 entities. Figure 20 shows all entities and relationships with their cardinalities;
Figures 21 and 22 repeat them with every attribute, the primary key (PK, underlined) and foreign
keys (FK, italic). Each entity is stored in its own JSON Lines text file (Table 9).
*Figure 20: E-R overview of the entire system (entities, relationships, cardinalities)*

<!-- page 48 -->
*Figure 21: E-R detail, part A: accounts, authentication, money and administration*

<!-- page 49 -->
*Figure 22: E-R detail, part B: catalog, reviews, moderation and AI data*

## 3.1 Data Dictionary

Types: str, int, float (money stored with 2 decimals), bool, datetime (YYYY-MM-DD HH:MM:SS).
IDs are strings with a prefix and a 4-digit counter (for example U-0007, B-0012) produced by
FileStore.next_id().
*Table 9: Entities, files and keys*
Entity File PK FK Other attributes (type)
USER users.txt user_id -
username (str, unique), full_name, email (str);
role {RC,VC,SU}; status
{ACTIVE,SUSPENDED}; balance (float);
warnings, purchase_count (int); total_spent
(float); promo_purchases (int); promo_spent
(float); created_at
BIOMETRIC biometrics.txt template_id user_id -> USER method {FACE,VOICE}; vector_path (str, .npy); enrolled_at
LOGIN_ATTEMP
T login_attempts.txt attempt_id username -> USER.username method; success (bool); score (float); timestamp
BOOK books.txt book_id added_by -> USER (SU)
title, author, category, keywords, description
(str); pub_year (int); price (float); cover_path,
cover_vec_path, text_path (str);
browse_count, purchase_count, rating_count
(int); weighted_avg (float); list_status
{NONE,NO_ORDER,TO_ORDER}; added_at
TRANSACTION transactions.txt txn_id
user_id -> USER;
book_id -> BOOK
(nullable)
type {DEPOSIT,PURCHASE,FINE}; amount
(float, signed); balance_after (float); note;
timestamp

<!-- page 50 -->
Entity File PK FK Other attributes (type)
PURCHASE purchases.txt purchase_id
user_id -> USER;
book_id -> BOOK;
txn_id ->
TRANSACTION
list_price, discount, price_paid (float);
timestamp
REVIEW reviews.txt review_id book_id -> BOOK; user_id -> USER
rating (int 1-5); original_text, display_text (str);
taboo_count (int); status
{PUBLISHED,BLOCKED}; verified_buyer
(bool); weight (float); timestamp
WARNING warnings.txt warning_id user_id -> USER; review_id -> REVIEW reason (str); timestamp
TABOO_WORD taboo_words.txt word added_by -> USER (SU) added_at
BROWSE_EVEN
T
browse_history.tx
t event_id user_id -> USER; book_id -> BOOK action {VIEW,SEARCH_HIT}; timestamp
CHAT_MESSAG
E chat_log.txt msg_id user_id -> USER (nullable for Visitors) session_id, role, question, answer (str); source {RAG,GENERAL,ADMIN,DENIED,ERROR}; timestamp
READING_PRO
GRESS
reading_progress
.txt progress_id user_id -> USER; book_id -> BOOK chapter (int); last_action (str); updated_at
STATUS_CHAN
GE
status_changes.t
xt change_id user_id -> USER from_role, to_role, from_status, to_status, reason (str); timestamp
ADMIN_ACTION admin_actions.txt action_id
su_id -> USER;
target_user_id ->
USER (nullable)
action
{REOPEN,ADD_BOOK,TABOO_ADD,TABOO
_EDIT,TABOO_REMOVE}; detail; timestamp
RAG_CHUNK rag_chunks.txt chunk_id book_id -> BOOK (nullable) source {BOOK,POLICY,CATALOG}; scope {PUBLIC,CUSTOMER,ADMIN}; text (str); vector_path (str)

## 3.2 Relationships

*Table 10: Relationships and cardinalities*
Relationship Cardinality Meaning
USER enrolls BIOMETRIC 1 : 1..2 Each account has a face template, a voice template, or both.
USER owns TRANSACTION 1 : N Every deposit, purchase and fine belongs to one user (the ledger).
USER makes PURCHASE / BOOK sold in
PURCHASE 1 : N / 1 : N PURCHASE resolves the many-to-many between users and books.
TRANSACTION settles PURCHASE 1 : 0..1 A PURCHASE transaction has exactly one purchase record; deposits and fines have none.
USER writes REVIEW / BOOK receives
REVIEW 1 : N / 1 : N Reviews link customers and books.
REVIEW triggers WARNING 1 : 0..1 Only a blocked review creates a warning.

<!-- page 51 -->
Relationship Cardinality Meaning
USER receives WARNING 1 : N The user's warnings counter equals the number of warnings since the last reopen.
USER (SU) adds BOOK / maintains
TABOO_WORD / performs ADMIN_ACTION 1 : N Administrative ownership and audit trail.
USER browses BROWSE_EVENT / BOOK
viewed in BROWSE_EVENT 1 : N History used by the recommender (R4).
USER asks CHAT_MESSAGE 0..1 : N Visitor messages have no user_id.
USER reads READING_PROGRESS / BOOK
tracked in 1 : N One progress row per user and book.
USER undergoes STATUS_CHANGE 1 : N History of promotions, demotions, suspensions and reopenings.
BOOK chunked into RAG_CHUNK 1 : N Book text split for retrieval; policy and catalog chunks have no book.
Example records (one line each in their files):
users.txt:  {"user_id":"U-0001","username":"selina","full_name":"Selina
    Zhu","email":"selina@example.com",
             "role":"VC","status":"ACTIVE","balance":40.0,"warnings":0,"purchase_count":8,
             "total_spent":214.5,"promo_purchases":8,"promo_spent":214.5,"created_at":"2026-
11-01 10:00:00"}
reviews.txt: {"review_id":"R-0004","book_id":"B-0001","user_id":"U-0001","rating":4,
             "original_text":"Great book, though the middle part felt a bit dumb at times.",
             "display_text":"Great book, though the middle part felt a bit **** at
                 times.","taboo_count":1,
             "status":"PUBLISHED","verified_buyer":true,"weight":2.0,"timestamp":"2026-11-15
                 00:53:14"}

<!-- page 52 -->

# 4. Detailed Design

This section gives pseudo-code for every method of every class in Figure 1: 21 classes (the screens
grouped as one) and 107 methods. For each method it states the input, the output and the main
logic, including the error each method raises for the exceptional scenarios of Section 2.

## 4.1 Conventions

- x <- y assigns; fs is the shared FileStore; now() returns the current timestamp.
- Records are dictionaries; r.field reads a field. Money is rounded to 2 decimals.
- Methods signal problems by raising a named error (ValueError, PermissionError,
PurchaseError, LoginError, ...). The screen that called the method catches it and shows its
message; no other state is changed.
- session.require(roles) re-reads the user from file before any action, so promotions,
demotions and suspensions made a moment earlier are always respected.
- Rule numbers (R1-R15) refer to Table 2.

## 4.2 Program Flow (Phase I flowcharts)

The four flowcharts from Phase I summarize the control flow the classes implement: the overall
application flow (handled by MainWindow and AuthService), purchasing (PurchaseService), the
chatbot (ChatbotService) and review moderation (ReviewService, ModerationEngine,
RatingService).

<!-- page 53 -->
*Figure 23: Overall application flow (Phase I, Fig. 3.2-1)*
 Figure 24: Book purchasing flow (Phase I, Fig. 3.2-2)

<!-- page 54 -->
*Figure 25: AI chatbot flow (Phase I, Fig. 3.2-3)*
*Figure 26: Review moderation and rating flow (Phase I,*
Fig. 3.2-4)

## 4.3 Class and Method Summary

*Table 11: Classes and their methods*
Class Layer Methods
FileStore Persistence load, append, save_all, update, find, next_id
Session Control start, end, refresh, require
AuthService Control register, login, logout, record_attempt, is_locked

<!-- page 55 -->
Class Layer Methods
BiometricEngine AI detect_face, face_embedding, voice_embedding, enroll, verify, cosine
CatalogService Control browse, search, search_by_cover, get_details, record_browse
CoverIndex AI build, embed, add, query
RecommendationEngine AI home_books, top_popular, personalized, build_profile, score
WalletService Control deposit, get_balance, get_ledger, post_transaction, charge_fine
PurchaseService Control purchase, final_price, already_owned
StatusManager Control evaluate_promotion, demote, suspend, can_reopen, reopen, log_change
ReviewService Control submit, is_verified_buyer, list_reviews
ModerationEngine AI tokenize, find_taboo, mask, moderate
WarningService Control issue, apply_consequences, get_warnings
RatingService Control recalculate, classify, get_list, recalculate_all
TabooService Control list_words, add_word, update_word, remove_word
AdminService Control add_book, validate_book, list_suspended, reopen_account, log_action
ChatbotService Control ask, classify_intent, is_permitted, build_prompt, account_context, admin_context, log
RAGRetriever AI build_index, chunk, index_book, retrieve
LLMClient AI is_available, generate, embed
ReadingCompanion Control open, load_chapter, summarize, explain, define, quiz, ask, save_progress
GUI classes (Tkinter) Presentation
MainWindow.run, MainWindow.build_sidebar, MainWindow.show,
MainWindow.on_logout, HomeScreen.render, LoginScreen.on_capture,
RegisterScreen.on_submit, CatalogScreen.on_search,
BookDetailScreen.render, WalletScreen.render, ChatScreen.on_send,
CompanionScreen.on_action, AdminScreens: on_add_book

## 4.4 FileStore

The only class that reads or writes files. A table is data/<table>.txt with one JSON object per
line. A process-wide lock serializes writes; full rewrites go to a temporary file that atomically replaces
the original, so a crash never leaves a half-written table.
Attributes: dir: str (data folder); lock: Lock
```text
load(table) -> list[dict]
INPUT : table name, e.g. "users"
OUTPUT: list of records (empty list if the file does not exist)
  path <- dir + "/" + table + ".txt"
  IF path does not exist THEN RETURN []
  records <- []
  FOR EACH line IN open(path):
      IF line is not blank THEN records.append(json_parse(line))
  RETURN records
append(table, record) -> dict
INPUT : table name, record (dict)
OUTPUT: the same record
  WITH lock:
      open dir/table.txt for appending
      write json_dump(record) + newline
  RETURN record
save_all(table, records) -> None
INPUT : table name, full list of records
OUTPUT: none (file replaced)
  tmp <- dir/table.txt.tmp
  WITH lock:
      write every record as one JSON line to tmp
      os.replace(tmp, dir/table.txt)        // atomic swap
update(table, key, value, changes) -> dict
INPUT : table, key field, key value, dict of new field values
OUTPUT: the updated record; raises KeyError if none matched
  records <- load(table)
  hit <- None
  FOR EACH r IN records:
      IF r[key] = value THEN r.update(changes); hit <- r
  IF hit is None THEN RAISE KeyError(table, key, value)
  save_all(table, records)
  RETURN hit
find(table, key, value) -> dict | None
INPUT : table, key field, value
OUTPUT: first matching record or None
  FOR EACH r IN load(table): IF r[key] = value THEN RETURN r
  RETURN None
next_id(table, prefix) -> str
INPUT : table, prefix such as "U", "B", "R"
OUTPUT: new id, e.g. "R-0013"
  nums <- [integer after the last "-" of each record's id IN load(table)]
  n <- (max(nums) + 1) IF nums not empty ELSE 1
  RETURN prefix + "-" + zero_pad(n, 4)
```

## 4.5 Session

Holds who is using the application. A Visitor session has user = None and role VS. wallet_only is
true when a suspended customer signs in.
Attributes: user: dict | None; role: {VS, RC, VC, SU}; wallet_only: bool; session_id: str
```text
start(user) -> None
INPUT : user record from users.txt
  self.user <- user
  self.role <- user.role
  self.wallet_only <- (user.status = "SUSPENDED")
  self.session_id <- random_uuid()
end() -> None
  self.user <- None; self.role <- "VS"; self.wallet_only <- False
  self.session_id <- random_uuid()
refresh() -> None
// re-read the user so role/status changes made by other services are visible
  IF self.user is not None THEN
      self.user <- FileStore.find("users", "user_id", self.user.user_id)
      self.role <- self.user.role
      self.wallet_only <- (self.user.status = "SUSPENDED")
require(*roles, active=True) -> None
INPUT : allowed roles; whether an ACTIVE account is needed
OUTPUT: none; raises PermissionError
  refresh()
  IF self.role NOT IN roles THEN RAISE PermissionError("Not available for your account type")
  IF active AND self.wallet_only THEN RAISE PermissionError("Your account is suspended")
```

## 4.6 AuthService

Registration, sign-in and sign-out (UC-01, UC-02). Uses BiometricEngine for the samples and logs
every attempt.
Attributes: fs: FileStore; bio: BiometricEngine; MAX_FAILS = 3; LOCK_MINUTES = 5
```text
register(full_name, username, email, face_img, voice_clip=None) -> dict
INPUT : form values; face image (may be None if voice given); optional voice clip
OUTPUT: new user record; raises RegistrationError(list of problems)
  problems <- []
  IF NOT matches(username, "^[A-Za-z0-9_]{3,20}$") THEN problems.add("username")
  IF fs.find("users", "username", lower(username)) THEN problems.add("username taken")
  IF full_name is blank THEN problems.add("full name")
  IF NOT matches(email, "^[^@ ]+@[^@ ]+\.[^@ ]+$") THEN problems.add("email")
  IF face_img is None AND voice_clip is None THEN problems.add("biometric sample")
  IF problems THEN RAISE RegistrationError(problems)
  uid <- fs.next_id("users", "U")
  saved <- []
  TRY
      IF face_img THEN saved.add(bio.enroll(uid, "FACE", face_img))      // raises NoFaceError
      IF voice_clip THEN saved.add(bio.enroll(uid, "VOICE", voice_clip))
      user <- {user_id: uid, username: lower(username), full_name, email,
               role: "RC", status: "ACTIVE", balance: 0.00, warnings: 0,
               purchase_count: 0, total_spent: 0.00, promo_purchases: 0,
               promo_spent: 0.00, created_at: now()}
      fs.append("users", user)
  EXCEPT any error:
      delete files in saved; delete their biometrics.txt rows     // no half account
      RE-RAISE
  RETURN user
login(username, method, sample) -> Session
INPUT : username, "FACE" or "VOICE", captured image or audio
OUTPUT: started Session; raises LoginError(kind, attempts_left)
  user <- fs.find("users", "username", lower(username))
  IF user is None THEN RAISE LoginError("UNKNOWN_USER")
  IF is_locked(user.username) THEN RAISE LoginError("LOCKED")
  (ok, score) <- bio.verify(user.user_id, method,
      sample)   // NoFaceError propagates: not counted
  record_attempt(user.username, method, ok, score)
  IF NOT ok THEN
      fails <- consecutive failures for username in login_attempts.txt
      IF fails >= MAX_FAILS THEN RAISE LoginError("LOCKED")
      RAISE LoginError("NO_MATCH", attempts_left = MAX_FAILS - fails)
  session <- Session(); session.start(user)
  RETURN session
logout(session) -> None
  session.end()
  MainWindow.show("home")
record_attempt(username, method, success, score) -> None
  fs.append("login_attempts", {attempt_id: fs.next_id("login_attempts","LA"), username,
           method, success, score: round(score, 3), timestamp: now()})
is_locked(username) -> bool
OUTPUT: True if the last MAX_FAILS attempts all failed within LOCK_MINUTES
  recent <- last MAX_FAILS attempts of username in login_attempts.txt (by timestamp)
  IF len(recent) < MAX_FAILS THEN RETURN False
  IF any r.success IN recent THEN RETURN False
  RETURN now() - recent[-1].timestamp < LOCK_MINUTES minutes
```

## 4.7 BiometricEngine

Face and voice matching with embeddings. YOLOv8-face finds the face box; a FaceNet model turns
the crop into a 512-number vector; Resemblyzer turns a voice clip into a 256-number vector.
Matching is cosine similarity against the stored vector (R2).
Attributes: detector: YOLO model; face_net: FaceNet model; voice_enc: Resemblyzer encoder;
FACE_T = 0.60; VOICE_T = 0.75
```text
detect_face(image) -> image
INPUT : RGB frame from the webcam (OpenCV)
OUTPUT: 160x160 face crop; raises NoFaceError
  boxes <- detector.predict(image, confidence >= 0.5)
  IF len(boxes) = 0 THEN RAISE NoFaceError("no face")
  IF len(boxes) > 1 THEN RAISE NoFaceError("several faces")
  RETURN resize(crop(image, boxes[0], margin 10%), 160, 160)
face_embedding(crop) -> vector
  v <- face_net(normalize_pixels(crop))
  RETURN v / norm(v)
voice_embedding(audio) -> vector
INPUT : mono 16 kHz audio
  IF duration(audio) < 2 seconds THEN RAISE NoVoiceError("too short")
  v <- voice_enc.embed_utterance(trim_silence(audio))
  RETURN v / norm(v)
enroll(user_id, method, sample) -> str
OUTPUT: path of the saved vector
  v <- face_embedding(detect_face(sample)) IF method = "FACE" ELSE voice_embedding(sample)
  path <- "data/biometrics/" + user_id + "_" + lower(method) + ".npy"
  save_numpy(path, v)
  fs.append("biometrics", {template_id: fs.next_id("biometrics","T"), user_id,
            method, vector_path: path, enrolled_at: now()})
  RETURN path
verify(user_id, method, sample) -> (bool, float)
OUTPUT: (match?, similarity score)
  t <- record in biometrics.txt with user_id and method
  IF t is None OR file t.vector_path missing THEN RAISE TemplateMissingError
  stored <- load_numpy(t.vector_path)
  live <- face_embedding(detect_face(sample)) IF method = "FACE" ELSE voice_embedding(sample)
  score <- cosine(stored, live)
  threshold <- FACE_T IF method = "FACE" ELSE VOICE_T
  RETURN (score >= threshold, score)
cosine(a, b) -> float
  RETURN dot(a, b) / (norm(a) * norm(b))
```

## 4.8 CatalogService

Browsing, text search, cover search and the details page (UC-04, UC-05).
Attributes: fs: FileStore; covers: CoverIndex; PAGE = 12
```text
browse(category=None, sort="title", page=1) -> list[dict]
  books <- fs.load("books")
  IF category THEN books <- [b IN books WHERE b.category = category]
  sort books by sort key ("title", "price", "weighted_avg" desc, "pub_year" desc)
  RETURN books[(page-1)*PAGE : page*PAGE]
search(query, field) -> list[dict]
INPUT : text or "YYYY-YYYY"; field IN {title, author, keyword, year}
OUTPUT: matching books, best first; raises ValueError for a bad year range
  q <- lower(trim(query))
  IF q = "" THEN RETURN browse()
  books <- fs.load("books"); results <- []
  FOR EACH b IN books:
      IF field = "year" THEN
          (lo, hi) <- parse_range(q)              // raises ValueError if lo > hi or
              non-numeric
          IF lo <= b.pub_year <= hi THEN results.add((0, b))
      ELSE
          text <- lower(b.title) IF field = "title" ELSE
                  lower(b.author) IF field = "author" ELSE lower(b.keywords + " " +
                      b.description)
          IF text = q THEN results.add((0, b))          // exact
          ELSE IF text startswith q THEN results.add((1, b))
          ELSE IF q IN text THEN results.add((2, b))
  RETURN [b FOR (rank, b) IN sort(results by rank, then title)]
search_by_cover(image) -> list[dict]
OUTPUT: up to 5 books; raises ValueError if the file is not an image
  IF image cannot be opened as JPG/PNG THEN RAISE ValueError("not an image")
  hits <- covers.query(covers.embed(image), k = 5)        // [(book_id, similarity)]
  hits <- [h IN hits WHERE h.similarity >= 0.25]
  RETURN [fs.find("books", "book_id", h.book_id) FOR h IN hits]
get_details(book_id, session) -> dict
OUTPUT: book with reviews and display price; raises NotFound
  book <- fs.find("books", "book_id", book_id)
  IF book is None THEN RAISE NotFound
  record_browse(session, book_id)
  book.reviews <- ReviewService.list_reviews(book_id)
  book.display_price <- PurchaseService.final_price(session.user,
      book).paid IF session.user ELSE book.price
  RETURN book
record_browse(session, book_id) -> None
  b <- fs.find("books", "book_id", book_id)
  fs.update("books", "book_id", book_id, {browse_count: b.browse_count + 1})
  IF session.role IN {RC, VC} THEN
      fs.append("browse_history", {event_id: fs.next_id("browse_history","E"),
                user_id: session.user.user_id, book_id, action: "VIEW", timestamp: now()})
```

## 4.9 CoverIndex

Image search over book covers with OpenCLIP. Each cover's vector is stored in
data/covers/<book_id>.npy; the index is the in-memory matrix of those vectors.
Attributes: model: OpenCLIP ViT-B/32; ids: list[str]; matrix: N x 512 array
```text
build() -> None
// called once at start-up
  ids <- []; rows <- []
  FOR EACH b IN fs.load("books") WHERE b.cover_path exists:
      IF b.cover_vec_path missing THEN add(b.book_id, open_image(b.cover_path))
      ids.add(b.book_id); rows.add(load_numpy(b.cover_vec_path))
  matrix <- stack(rows)
embed(image) -> vector
  v <- model.encode_image(preprocess(image))
  RETURN v / norm(v)
add(book_id, image) -> str
  v <- embed(image); path <- "data/covers/" + book_id + ".npy"
  save_numpy(path, v)
  fs.update("books", "book_id", book_id, {cover_vec_path: path})
  ids.add(book_id); matrix <- append_row(matrix, v)
  RETURN path
query(vector, k=5) -> list[(str, float)]
  IF ids is empty THEN RETURN []
  sims <- matrix x vector                 // cosine, vectors are unit length
  top <- indexes of the k largest sims
  RETURN [(ids[i], sims[i]) FOR i IN top]
```

## 4.10 RecommendationEngine

Chooses the three home-page books: popular (R3) for Visitors and Super-Users, personalized (R4)
for customers.
Attributes: fs: FileStore; W_BUY = 3; W_VIEW = 1
```text
home_books(session) -> (str, list[dict])
OUTPUT: (section title, 3 books)
  IF session.role IN {VS, SU} THEN RETURN ("Top 3 Most Popular", top_popular(3))
  recs <- personalized(session.user.user_id, 3)
  IF recs is empty THEN RETURN ("Popular right now", top_popular(3))
  RETURN ("Recommended for You", recs)
top_popular(k=3, exclude=set()) -> list[dict]
  books <- [b IN fs.load("books") WHERE b.book_id NOT IN exclude]
  sort books by (b.browse_count + 3 * b.purchase_count) desc, then weighted_avg desc,
      then title
  RETURN books[0:k]
personalized(user_id, k=3) -> list[dict]
  profile <- build_profile(user_id)
  IF profile is empty THEN RETURN []
  owned <- {p.book_id FOR p IN fs.load("purchases") WHERE p.user_id = user_id}
  scored <- [(score(b, profile), b) FOR b IN fs.load("books") WHERE b.book_id NOT IN owned]
  picks <- [b FOR (s, b) IN sort(scored desc) WHERE s > 0][0:k]
  IF len(picks) < k THEN picks += top_popular(k - len(picks), exclude = owned + ids(picks))
  RETURN picks
build_profile(user_id) -> dict[str, float]
OUTPUT: weights such as {"cat:Classic": 4, "auth:Jane Austen": 3, "kw:romance": 1}
  profile <- empty counter
  FOR EACH p IN purchases of user_id:   add_book_terms(profile, book of p, W_BUY)
  FOR EACH e IN browse events of user_id: add_book_terms(profile, book of e, W_VIEW)
  RETURN profile
  // add_book_terms: profile["cat:"+category] += w; profile["auth:"+author] += w;
  //                 for each keyword kw: profile["kw:"+kw] += w
score(book, profile) -> float
  s <- profile["cat:" + book.category] + profile["auth:" + book.author]
  FOR EACH kw IN book.keywords: s <- s + profile["kw:" + kw]
  RETURN s + 0.1 * book.weighted_avg          // small tie-breaker for better-rated books
```

## 4.11 WalletService

Balance and ledger (UC-07). Every change of balance goes through post_transaction, so the
ledger always explains the balance.
Attributes: fs: FileStore; status: StatusManager; MAX_DEPOSIT = 10000.00; FINE = 1.00
```text
deposit(session, amount_text) -> float
INPUT : signed-in customer (wallet-only allowed); amount as typed
OUTPUT: new balance; raises ValueError
  session.require(RC, VC, active = False)
  amount <- parse_decimal(amount_text)                 // ValueError if not a number
  IF amount <= 0 OR amount > MAX_DEPOSIT OR has_more_than_2_decimals(amount) THEN RAISE
      ValueError
  txn <- post_transaction(session.user.user_id, "DEPOSIT", +amount, None, "Add funds")
  IF session.user.status = "SUSPENDED" AND txn.balance_after >= 0 THEN
      show_note("A Super-User can now reactivate your account")
  RETURN txn.balance_after
get_balance(user_id) -> float
  RETURN fs.find("users", "user_id", user_id).balance
get_ledger(user_id) -> list[dict]
  RETURN [t IN fs.load("transactions") WHERE t.user_id = user_id] sorted by timestamp desc
post_transaction(user_id, type, amount, book_id, note) -> dict
INPUT : amount is signed (+deposit, -purchase, -fine)
OUTPUT: transaction record
  user <- fs.find("users", "user_id", user_id)
  new_balance <- round(user.balance + amount, 2)
  txn <- {txn_id: fs.next_id("transactions","X"), user_id, type, amount,
          balance_after: new_balance, book_id, note, timestamp: now()}
  fs.append("transactions", txn)
  fs.update("users", "user_id", user_id, {balance: new_balance})
  RETURN txn
charge_fine(user_id, book_id) -> dict
OUTPUT: fine transaction; suspends the account if the balance becomes negative (R7)
  txn <- post_transaction(user_id, "FINE", -FINE, book_id, "Insufficient funds")
  IF txn.balance_after < 0 THEN status.suspend(user_id, "negative balance")
  RETURN txn
```

## 4.12 PurchaseService

Buying a book (UC-08) including the VIP discount (UC-09). Figure 24 (the Phase I purchase
flowchart) shows the same logic as a flowchart.
Attributes: fs: FileStore; wallet: WalletService; status: StatusManager; VIP_RATE = 0.10
```text
purchase(session, book_id) -> Receipt
INPUT : signed-in ACTIVE customer, book id
OUTPUT: Receipt(list_price, discount, paid, balance, promoted); raises PurchaseError
  session.require(RC, VC)                                   // re-reads role and status
  user <- session.user
  book <- fs.find("books", "book_id", book_id)
  IF book is None THEN RAISE PurchaseError("Book unavailable")
  IF already_owned(user.user_id, book_id) THEN RAISE PurchaseError("You already own this
      book")
  price <- final_price(user, book)
  IF user.balance < price.paid THEN
      fine <- wallet.charge_fine(user.user_id, book_id)
      session.refresh()
      RAISE PurchaseError("Insufficient funds: $1.00 fine charged",
          suspended = session.wallet_only)
  txn <- wallet.post_transaction(user.user_id, "PURCHASE", -price.paid, book_id,
                                 book.title + (" (VIP -10%)" IF price.discount > 0 ELSE ""))
  fs.append("purchases", {purchase_id: fs.next_id("purchases","P"), user_id: user.user_id,
            book_id, txn_id: txn.txn_id, list_price: book.price, discount: price.discount,
            price_paid: price.paid, timestamp: now()})
  u <- fs.find("users", "user_id", user.user_id)
  fs.update("users", "user_id", u.user_id, {purchase_count: u.purchase_count + 1,
            total_spent: u.total_spent + price.paid, promo_purchases: u.promo_purchases + 1,
            promo_spent: u.promo_spent + price.paid})
  fs.update("books", "book_id", book_id, {purchase_count: book.purchase_count + 1})
  promoted <- status.evaluate_promotion(u.user_id)
  session.refresh()
  RETURN Receipt(book.price, price.discount, price.paid, txn.balance_after, promoted)
final_price(user, book) -> Price
OUTPUT: Price(list, discount, paid)
  u <- fs.find("users", "user_id", user.user_id)            // never trust a cached role
  discount <- round(book.price * VIP_RATE, 2) IF u.role = "VC" ELSE 0.00
  RETURN Price(book.price, discount, round(book.price - discount, 2))
already_owned(user_id, book_id) -> bool
  RETURN any p IN fs.load("purchases") WHERE p.user_id = user_id AND p.book_id = book_id
```

## 4.13 StatusManager

The only class that changes a user's role or status (R5, R8, R10). Every change is written to
status_changes.txt.
Attributes: fs: FileStore; PROMO_PURCHASES = 3; PROMO_SPENT = 200.00
```text
evaluate_promotion(user_id) -> bool
OUTPUT: True if the user was promoted now
  u <- fs.find("users", "user_id", user_id)
  IF u.role = "RC" AND u.status = "ACTIVE" AND
     (u.promo_purchases > PROMO_PURCHASES OR u.promo_spent > PROMO_SPENT) THEN
      log_change(u, to_role = "VC", to_status = u.status, reason = "promotion")
      fs.update("users", "user_id", user_id, {role: "VC"})
      RETURN True
  RETURN False
demote(user_id, reason) -> dict
  u <- fs.find("users", "user_id", user_id)
  IF u.role <> "VC" THEN RETURN u
  log_change(u, "RC", u.status, reason)
  RETURN fs.update("users", "user_id", user_id, {role: "RC", promo_purchases: 0,
      promo_spent: 0.00})
suspend(user_id, reason) -> dict
  u <- fs.find("users", "user_id", user_id)
  IF u.status = "SUSPENDED" THEN RETURN u
  log_change(u, u.role, "SUSPENDED", reason)
  RETURN fs.update("users", "user_id", user_id, {status: "SUSPENDED"})
can_reopen(user) -> (bool, str)
  IF user.status <> "SUSPENDED" THEN RETURN (False, "Account is not suspended")
  IF user.balance < 0 THEN
      RETURN (False, "Customer must deposit at least $" + format(-user.balance))
  RETURN (True, "")
reopen(su_id, user_id) -> dict
OUTPUT: updated user; raises ReopenError
  u <- fs.find("users", "user_id", user_id)
  (ok, why) <- can_reopen(u)
  IF NOT ok THEN RAISE ReopenError(why)
  log_change(u, u.role, "ACTIVE", "reopened by " + su_id)
  RETURN fs.update("users", "user_id", user_id, {status: "ACTIVE", warnings: 0})
log_change(user, to_role, to_status, reason) -> None
  fs.append("status_changes", {change_id: fs.next_id("status_changes","SC"),
            user_id: user.user_id, from_role: user.role, to_role,
            from_status: user.status, to_status, reason, timestamp: now()})
```

## 4.14 ReviewService

Submitting and listing reviews (UC-10). This class is implemented and tested in the prototype
(Section 5.2). Figure 26 (Phase I review flowchart) shows the same flow.
Attributes: fs: FileStore; moderation: ModerationEngine; warnings: WarningService; ratings:
RatingService; W_VERIFIED = 2.0; W_OTHER = 1.0
```text
submit(session, book_id, rating, text) -> SubmitResult
INPUT : signed-in ACTIVE customer, book id, stars 1-5, comment
OUTPUT: SubmitResult(status, message, review, consequence)
  session.require(RC, VC)                      // PermissionError if visitor/SU/suspended
  IF rating NOT IN 1..5 THEN RAISE ValueError("Choose a rating from 1 to 5 stars")
  text <- trim(text)
  IF len(text) = 0 OR len(text) > 1000 THEN RAISE ValueError("Comment must be 1-1000
      characters")
  mod <- moderation.moderate(text)
  verified <- is_verified_buyer(session.user.user_id, book_id)
  review <- {review_id: fs.next_id("reviews","R"), book_id, user_id: session.user.user_id,
             rating, original_text: text, display_text: mod.display_text,
             taboo_count: mod.count, status: mod.status, verified_buyer: verified,
             weight: W_VERIFIED IF verified ELSE W_OTHER, timestamp: now()}
  fs.append("reviews", review)
  IF mod.status = "BLOCKED" THEN
      consequence <- warnings.issue(session.user.user_id, review.review_id, "blocked comment")
      session.refresh()
      RETURN SubmitResult("BLOCKED", warning_message(session.user, mod.count, consequence),
                          review, consequence)
  ratings.recalculate(book_id)
  RETURN SubmitResult("PUBLISHED", "Review published" + masked_note(mod.count), review, "")
is_verified_buyer(user_id, book_id) -> bool
  RETURN PurchaseService.already_owned(user_id, book_id)
list_reviews(book_id) -> list[dict]
  names <- {u.user_id: u.full_name FOR u IN fs.load("users")}
  rs <- [r IN fs.load("reviews") WHERE r.book_id = book_id AND r.status = "PUBLISHED"]
  FOR EACH r IN rs: r.author <- names[r.user_id]
  RETURN rs sorted by timestamp desc          // display_text only; original_text never shown
```

## 4.15 ModerationEngine

Finds and masks taboo words (R9). Matching is case-insensitive on whole words, so 'class' does not
match 'ass'.
Attributes: taboo: TabooService; BLOCK_ABOVE = 3
```text
tokenize(text) -> list[(str, int, int)]
OUTPUT: each word with its start and end position
  RETURN [(m.text, m.start, m.end) FOR m IN regex_find_all("[A-Za-z']+", text)]
find_taboo(text) -> list[(str, int, int)]
  words <- set(taboo.list_words())             // already lower case
  RETURN [(w, s, e) FOR (w, s, e) IN tokenize(text) WHERE lower(w) IN words]
mask(text, matches) -> str
  chars <- list(text)
  FOR EACH (w, s, e) IN matches: chars[s:e] <- "*" repeated (e - s)
  RETURN join(chars)
moderate(text) -> ModerationResult
OUTPUT: ModerationResult(status, display_text, count)
  matches <- find_taboo(text)
  IF len(matches) > BLOCK_ABOVE THEN RETURN ModerationResult("BLOCKED", "", len(matches))
  RETURN ModerationResult("PUBLISHED", mask(text, matches), len(matches))
```

## 4.16 WarningService

Records warnings and applies their consequences (UC-11, R10).
Attributes: fs: FileStore; status: StatusManager; RC_SUSPEND_ABOVE = 2
```text
issue(user_id, review_id, reason) -> str
OUTPUT: consequence "", "DEMOTED" or "SUSPENDED"
  fs.append("warnings", {warning_id: fs.next_id("warnings","W"), user_id, review_id,
            reason, timestamp: now()})
  u <- fs.find("users", "user_id", user_id)
  fs.update("users", "user_id", user_id, {warnings: u.warnings + 1})
  RETURN apply_consequences(user_id)
apply_consequences(user_id) -> str
  u <- fs.find("users", "user_id", user_id)
  IF u.role = "VC" THEN status.demote(user_id, "blocked comment"); RETURN "DEMOTED"
  IF u.role = "RC" AND u.warnings > RC_SUSPEND_ABOVE THEN
      status.suspend(user_id, u.warnings + " warnings"); RETURN "SUSPENDED"
  RETURN ""
get_warnings(user_id) -> list[dict]
  RETURN [w IN fs.load("warnings") WHERE w.user_id = user_id] sorted by timestamp desc
```

## 4.17 RatingService

Weighted rating and the No-Order / To-Order lists (R12, R13, UC-18).
Attributes: fs: FileStore; MIN_RATINGS = 3
```text
recalculate(book_id) -> dict
  rs <- [r IN fs.load("reviews") WHERE r.book_id = book_id AND r.status = "PUBLISHED"]
  total_w <- sum(r.weight FOR r IN rs)
  avg <- round(sum(r.rating * r.weight FOR r IN rs) / total_w, 2) IF total_w > 0 ELSE 0
  book <- fs.update("books", "book_id", book_id, {rating_count: len(rs), weighted_avg: avg})
  RETURN fs.update("books", "book_id", book_id, {list_status: classify(book)})
classify(book) -> str
  IF book.rating_count > MIN_RATINGS AND book.weighted_avg < 2 THEN RETURN "NO_ORDER"
  IF book.rating_count > MIN_RATINGS AND book.weighted_avg > 4 THEN RETURN "TO_ORDER"
  RETURN "NONE"
get_list(list_type) -> list[dict]
INPUT : "NO_ORDER" or "TO_ORDER"
  books <- [b IN fs.load("books") WHERE b.list_status = list_type]
  RETURN books sorted by weighted_avg (asc for NO_ORDER, desc for TO_ORDER)
recalculate_all() -> int
  FOR EACH b IN fs.load("books"): recalculate(b.book_id)
  RETURN number of books
```

## 4.18 TabooService

Maintains taboo_words.txt (UC-16). Only Super-Users can change it.
Attributes: fs: FileStore
```text
list_words() -> list[str]
  RETURN sorted([r.word FOR r IN fs.load("taboo_words")])
add_word(session, word) -> list[str]
  session.require(SU)
  w <- lower(trim(word))
  IF w = "" OR " " IN w THEN RAISE ValueError("Enter a single word")
  IF w IN list_words() THEN RAISE ValueError("Already in the list")
  fs.append("taboo_words", {word: w, added_by: session.user.user_id, added_at: now()})
  AdminService.log_action(session, "TABOO_ADD", None, w)
  RETURN list_words()
update_word(session, old, new) -> list[str]
  session.require(SU)
  n <- lower(trim(new))
  IF n = "" OR " " IN n OR n IN list_words() THEN RAISE ValueError("Invalid or duplicate
      word")
  fs.update("taboo_words", "word", old, {word: n})        // KeyError -> list reloaded
  AdminService.log_action(session, "TABOO_EDIT", None, old + " -> " + n)
  RETURN list_words()
remove_word(session, word) -> list[str]
  session.require(SU)
  rows <- [r IN fs.load("taboo_words") WHERE r.word <> word]
  fs.save_all("taboo_words", rows)
  AdminService.log_action(session, "TABOO_REMOVE", None, word)
  RETURN list_words()
```

## 4.19 AdminService

Super-User operations on books and accounts (UC-15, UC-17).
Attributes: fs: FileStore; status: StatusManager; covers: CoverIndex; rag: RAGRetriever
```text
add_book(session, data, cover_file, text_file=None) -> str
OUTPUT: new book_id; raises ValidationError(list)
  session.require(SU)
  validate_book(data)
  bid <- fs.next_id("books", "B")
  book <- data + {book_id: bid, cover_path: copy cover_file to data/covers/,
                  text_path: copy text_file to data/texts/ IF text_file ELSE None,
                  added_by: session.user.user_id, browse_count: 0, purchase_count: 0,
                  rating_count: 0, weighted_avg: 0, list_status: "NONE",
                  indexed: False, added_at: now()}
  fs.append("books", book)
  TRY
      covers.add(bid, open_image(book.cover_path))
      IF book.text_path THEN rag.index_book(book)
      fs.update("books", "book_id", bid, {indexed: True})
  EXCEPT ModelUnavailable: pass             // indexed again at next start-up (E4)
  log_action(session, "ADD_BOOK", None, bid)
  RETURN bid
validate_book(data) -> None
  problems <- []
  FOR f IN [title, author, category, price, pub_year]: IF data[f] blank THEN problems.add(f)
  IF NOT is_number(data.price) OR data.price <= 0 THEN problems.add("price")
  IF NOT is_int(data.pub_year) OR data.pub_year > current_year THEN problems.add("year")
  IF any b IN fs.load("books") WITH lower(b.title) = lower(data.title)
                                AND lower(b.author) = lower(data.author)
      THEN problems.add("duplicate book")
  IF problems THEN RAISE ValidationError(problems)
list_suspended(session) -> list[dict]
  session.require(SU)
  users <- [u IN fs.load("users") WHERE u.status = "SUSPENDED"]
  FOR EACH u IN users: u.reason <- latest status_changes reason for u
  RETURN users
reopen_account(session, user_id) -> dict
  session.require(SU)
  u <- status.reopen(session.user.user_id, user_id)       // ReopenError shown to SU
  log_action(session, "REOPEN", user_id, "")
  RETURN u
log_action(session, action, target_user_id, detail) -> None
  fs.append("admin_actions", {action_id: fs.next_id("admin_actions","A"),
            su_id: session.user.user_id, target_user_id, action, detail, timestamp: now()})
```

## 4.20 ChatbotService

Role-aware chatbot (UC-12, UC-13, R14). Figure 25 (Phase I chatbot flowchart) shows the routing.
Attributes: fs: FileStore; rag: RAGRetriever; llm: LLMClient; PERMITTED = {VS: {STORE}, RC:
{STORE, ACCOUNT, GENERAL}, VC: {STORE, ACCOUNT, GENERAL}, SU: {STORE, ACCOUNT,
GENERAL, ADMIN}}
```text
ask(session, question) -> ChatResponse
INPUT : session (any role), question text
OUTPUT: ChatResponse(text, source)
  q <- trim(question)
  IF q = "" THEN RETURN ChatResponse("", "NONE")              // Send button disabled anyway
  intent <- classify_intent(q)
  IF NOT is_permitted(session.role, intent) THEN
      IF session.role = "VS" AND intent = "GENERAL" THEN
          resp <- ChatResponse("I can only answer questions about the store.", "DENIED")
      ELSE resp <- ChatResponse("That information isn't available for your account type.",
          "DENIED")
      log(session, q, resp); RETURN resp
  IF NOT llm.is_available() THEN
      IF intent = "ADMIN" THEN resp <- ChatResponse(table_text(admin_context(q)), "ADMIN")
      ELSE resp <- ChatResponse("The assistant is offline - please try again later.", "ERROR")
      log(session, q, resp); RETURN resp
  IF intent = "ADMIN" THEN
      facts <- admin_context(q); source <- "ADMIN"
  ELSE
      scopes <- {"PUBLIC"}
      facts <- rag.retrieve(q, scopes, k = 4)
      IF intent = "ACCOUNT" THEN facts <- facts + account_context(session.user)
      source <- "RAG" IF facts not empty ELSE "GENERAL"
  IF source = "GENERAL" AND session.role = "VS" THEN
      resp <- ChatResponse("I couldn't find that in the store's information.", "RAG")
  ELSE
      resp <- ChatResponse(llm.generate(build_prompt(q, facts, session.role), timeout = 30),
          source)
  log(session, q, resp)
  RETURN resp                 // GUI shows label [Store data] / [General AI] / [Admin data]
classify_intent(question) -> str
OUTPUT: "ADMIN", "ACCOUNT", "STORE" or "GENERAL"
  q <- lower(question)
  IF q contains any of {suspended, all users, warnings issued, revenue, sales, no-order,
                        to-order, total balance, every customer} THEN RETURN "ADMIN"
  IF q contains any of {my balance, my order, my purchase, my review, my warning,
                        my account, am i vip} THEN RETURN "ACCOUNT"
  IF q mentions a catalog title/author/category, price, stock, policy, discount, fine,
     vip, return, recommend THEN RETURN "STORE"
  label <- llm.generate("Classify as STORE or GENERAL: " + question, max_tokens = 3)
  RETURN "STORE" IF label = "STORE" ELSE "GENERAL"
is_permitted(role, intent) -> bool
  RETURN intent IN PERMITTED[role]
build_prompt(question, facts, role) -> str
  sys <- "You are the BookOrbit AI store assistant. Answer in at most 120 words. "
  IF facts not empty THEN
      sys <- sys + "Use ONLY the facts below. If they do not answer, say you don't know.\n"
              + numbered list of facts
  IF role <> "SU" THEN sys <- sys + "Never reveal other customers' data."
  RETURN sys + "\nQuestion: " + question
account_context(user) -> list[str]
  RETURN ["Balance: $" + user.balance, "Role: " + user.role, "Status: " + user.status,
          "Warnings: " + user.warnings,
          "Recent purchases: " + titles of last 5 purchases of user]
admin_context(question) -> list[str]
// computed from files, never invented by the LLM
  users <- fs.load("users")
  facts <- ["Suspended accounts: " + names of users with status SUSPENDED,
            "Customers by role: " + counts of RC / VC,
            "Total customer balances: $" + sum(u.balance FOR u IN users),
            "Sales this month: $" + sum(price_paid of purchases this month),
            "Warnings this month: " + count of warnings this month,
            "No-Order List: " + titles, "To-Order List: " + titles]
  RETURN [f IN facts WHERE f relates to keywords of question] OR facts
log(session, question, resp) -> None
  fs.append("chat_log", {msg_id: fs.next_id("chat_log","M"),
            user_id: session.user.user_id IF session.user ELSE None,
            session_id: session.session_id, role: session.role, question,
            answer: resp.text, source: resp.source, timestamp: now()})
```

## 4.21 RAGRetriever

Retrieval for the chatbot and the Reading Companion. Store policies, the catalog and book texts are
split into chunks, embedded with nomic-embed-text (through Ollama) and searched by cosine
similarity.
Attributes: fs: FileStore; llm: LLMClient; vectors: dict[chunk_id -> vector]; CHUNK_WORDS = 250;
OVERLAP = 40; MIN_SIM = 0.45
```text
build_index() -> None
// start-up: load existing vectors; create missing ones
  IF rag_chunks.txt is empty THEN
      FOR EACH paragraph IN data/policies.txt: add_chunk("POLICY", None, "PUBLIC", paragraph)
      FOR EACH b IN fs.load("books"):
          add_chunk("CATALOG", b.book_id, "PUBLIC",
                    b.title + " by " + b.author + ", " + b.category + ",
                        $" + b.price + ". " + b.description)
          IF b.text_path AND NOT b.indexed THEN index_book(b)
  FOR EACH c IN fs.load("rag_chunks"): vectors[c.chunk_id] <- load_numpy(c.vector_path)
chunk(text) -> list[str]
  words <- split(text)
  out <- []; i <- 0
  WHILE i < len(words):
      out.add(join(words[i : i + CHUNK_WORDS])); i <- i + CHUNK_WORDS - OVERLAP
  RETURN out
index_book(book) -> int
OUTPUT: number of chunks
  text <- strip_gutenberg_header_footer(read(book.text_path))
  n <- 0
  FOR EACH (chapter_no, chapter_text) IN split_chapters(text):
      FOR EACH piece IN chunk(chapter_text):
          add_chunk("BOOK", book.book_id, "PUBLIC", piece, chapter = chapter_no); n <- n + 1
  RETURN n
  // add_chunk: id <- next_id("rag_chunks","C"); v <- llm.embed(text);
  //   save v to data/rag/<id>.npy; append the chunk record; vectors[id] <- v
retrieve(query, scopes, k=4, book_id=None, chapter=None) -> list[str]
OUTPUT: up to k chunk texts, most similar first
  qv <- llm.embed(query)
  cands <- [c IN fs.load("rag_chunks") WHERE c.scope IN scopes
            AND (book_id is None OR c.book_id = book_id)
            AND (chapter is None OR c.chapter = chapter)]
  IF book_id is None THEN cands <- [c IN cands WHERE c.source <> "BOOK"]   // chatbot: no full
      texts
  scored <- [(cosine(qv, vectors[c.chunk_id]), c) FOR c IN cands]
  RETURN [c.text FOR (s, c) IN top k of scored WHERE s >= MIN_SIM]
```

## 4.22 LLMClient

Thin wrapper over the local Ollama HTTP API (no paid API, no internet).
Attributes: url = "http://localhost:11434"; model = "llama3.2:3b"; embed_model = "nomic-embed-
text"
```text
is_available() -> bool
  TRY  RETURN http_get(url + "/api/tags", timeout = 2).status = 200
  EXCEPT connection error: RETURN False
generate(prompt, max_tokens=300, timeout=30) -> str
  r <- http_post(url + "/api/generate",
                 {model, prompt, stream: False, options: {num_predict: max_tokens,
                     temperature: 0.3}},
                 timeout)
  IF r failed OR timed out THEN RAISE LLMUnavailable
  RETURN trim(r.json.response)
embed(text) -> vector
  r <- http_post(url + "/api/embeddings", {model: embed_model, prompt: text}, timeout = 15)
  IF r failed THEN RAISE ModelUnavailable
  v <- array(r.json.embedding)
  RETURN v / norm(v)
```

## 4.23 ReadingCompanion

Our creative feature (UC-14, R15): an AI reading assistant grounded in the book's own text, so
explanations quote the actual chapter rather than the LLM's memory.
Attributes: fs: FileStore; rag: RAGRetriever; llm: LLMClient
```text
open(session, book_id) -> CompanionState
OUTPUT: chapters, current chapter, owned flag; raises CompanionError
  session.require(RC, VC)
  book <- fs.find("books", "book_id", book_id)
  IF book.text_path is None THEN RAISE CompanionError("Not available for this book")
  owned <- PurchaseService.already_owned(session.user.user_id, book_id)
  p <- progress row for (user, book)
  chapter <- p.chapter IF p ELSE 1
  IF NOT owned THEN chapter <- 1
  RETURN CompanionState(book, chapter_titles(book), chapter, owned)
load_chapter(state, n) -> str
  IF NOT state.owned AND n > 1 THEN RAISE CompanionError("Buy the book to keep reading")
  text <- n-th chapter of strip_gutenberg_header_footer(read(state.book.text_path))
  save_progress(state, n, "read")
  RETURN text
summarize(state, n) -> str
  chunks <- rag.retrieve("summary of chapter " + n, {"PUBLIC"}, k = 6,
                        book_id = state.book.book_id, chapter = n)
  RETURN ask_llm("Summarize this chapter in 5 bullet points for a student.", chunks, state,
      "summarize")
explain(state, selection) -> str
  IF trim(selection) = "" THEN RAISE CompanionError("Select a passage first")
  chunks <- rag.retrieve(selection, {"PUBLIC"}, k = 3, book_id = state.book.book_id)
  RETURN ask_llm("Explain this passage in plain modern English, with its context: "
                 + quote(selection), chunks, state, "explain")
define(state, word) -> str
  chunks <- rag.retrieve(word, {"PUBLIC"}, k = 2, book_id = state.book.book_id,
                        chapter = state.chapter)
  RETURN ask_llm("Define '" + word + "' as it is used here (the book's era and meaning).",
                 chunks, state, "define")
quiz(state, n, count=3) -> list[Question]
  chunks <- rag.retrieve("key events of chapter " + n, {"PUBLIC"}, k = 6,
                        book_id = state.book.book_id, chapter = n)
  raw <- ask_llm("Write " + count + " multiple-choice questions as JSON
                  [{q, options[4], answer_index}] using only the text.", chunks, state,
                      "quiz")
  qs <- json_parse(raw)        // if invalid JSON: retry once, then show "Try again"
  RETURN [q IN qs WHERE len(q.options) = 4 AND 0 <= q.answer_index < 4]
ask(state, question) -> str
  chunks <- rag.retrieve(question, {"PUBLIC"}, k = 4, book_id = state.book.book_id)
  RETURN ask_llm(question, chunks, state, "ask")
  // ask_llm(instruction, chunks, state, action):
  //   IF NOT llm.is_available() THEN RAISE CompanionError("Assistant offline")
  //   answer <- llm.generate("You are a reading companion for '" + state.book.title +
  //             "'. Use only these excerpts:\n" + chunks + "\n" + instruction)
  //   save_progress(state, state.chapter, action); RETURN answer
save_progress(state, n, action) -> None
  row <- progress row for (state.user_id, state.book.book_id)
  IF row THEN fs.update("reading_progress", "progress_id", row.progress_id,
                        {chapter: n, last_action: action, updated_at: now()})
  ELSE fs.append("reading_progress", {progress_id: fs.next_id("reading_progress","RP"),
                 user_id: state.user_id, book_id: state.book.book_id, chapter: n,
                 last_action: action, updated_at: now()})
  state.chapter <- n
```

## 4.24 GUI classes (Tkinter)

Screens only display data and forward user actions to services; they hold no business rules. Every
handler catches the service's exceptions and shows their message in a banner (the pattern used in
the prototype). Figure 23 (Phase I overall flowchart) shows how the screens connect.
Attributes: MainWindow owns: session, all services, the sidebar frame and the current screen
frame
MainWindow.run() -> None
  fs <- FileStore(); create all services with fs
  CoverIndex.build(); RAGRetriever.build_index()        // background thread,
      splash text meanwhile
  session <- Session()                                  // Visitor
  build_sidebar(session.role); show("home"); tk.mainloop()

<!-- page 76 -->
MainWindow.build_sidebar(role, wallet_only=False) -> None
  items <- {VS: [Home, Browse, Search, Top Books, AI Chatbot, Sign In, Register],
            RC: [Home, Browse, Recommendations, My Orders, My Reviews, My Balance, AI Chatbot,
                Sign Out],
            VC: same as RC,
            SU: [Home, Manage Books, Manage Taboo Words, User Management, Reports, AI Chatbot,
                Sign Out]}[role]
  IF wallet_only THEN items <- [My Balance, Sign Out]
  draw items; bind each to show(screen_name)
MainWindow.show(name, **args) -> None
  destroy current screen frame
  screen <- SCREENS[name](self, **args)        // Home, Login, Register, Catalog, BookDetail,
  screen.render()                              // Wallet, Chat, Companion, Admin*
  IF session.wallet_only AND name <> "wallet" THEN show("wallet")
MainWindow.on_logout() -> None
  AuthService.logout(session); build_sidebar("VS"); show("home")
HomeScreen.render() -> None
  (title, books) <- RecommendationEngine.home_books(session)
  draw search bar; draw title; FOR EACH b IN books: draw_card(b, on_click = show("book",
      b.book_id))
  IF books is empty THEN draw "No books available yet"
  IF session.role = "VC" THEN draw VIP banner; IF role IN {RC,VC} THEN draw balance card
LoginScreen.on_capture() / on_submit() -> None
  frame <- webcam.read() IF tab = Face ELSE microphone.record(3 s)
  TRY  session <- AuthService.login(username_entry, tab, frame)
       MainWindow.session <- session; build_sidebar(session.role,
           session.wallet_only); show("home")
  EXCEPT NoFaceError: banner("Center your face in the frame")        // not counted
  EXCEPT LoginError e: banner(message_for(e.kind, e.attempts_left))
RegisterScreen.on_submit() -> None
  TRY  AuthService.register(name, username, email, captured_face, recorded_voice)
       banner_ok("Account created - please sign in"); show("login")
  EXCEPT RegistrationError e: outline the fields in e.problems
  EXCEPT NoFaceError e: banner(e.message + " - please retake"); retries += 1
       IF retries = 3 THEN show("home")
CatalogScreen.on_search() / on_cover_upload() / on_select(id) -> None
  on_search:       results <- CatalogService.search(query, field) OR browse(category)
  on_cover_upload: file <- askopenfilename(jpg/png); results <-
      CatalogService.search_by_cover(open(file))
  draw grid (12 per page) OR "No books found" + Clear filters
  on_select(id):   show("book", id)

<!-- page 77 -->
BookDetailScreen.render() / on_buy() / on_review() / on_companion() -> None
  render:       book <- CatalogService.get_details(id, session); draw details, reviews,
      buttons by role
  on_buy:       p <- PurchaseService.final_price(session.user, book)
                IF confirm("Buy for $" + p.paid + discount line) THEN
                    TRY r <- PurchaseService.purchase(session,
                        id); show receipt (+ "You are now VIP!")
                    EXCEPT PurchaseError e: banner(e); IF e.suspended THEN build_sidebar(role,
                        True); show("wallet")
  on_review:    r <- ReviewService.submit(session, id, stars,
      text); banner by r.status; re-render
  on_companion: show("companion", id)
WalletScreen.render() / on_deposit() -> None
  render:     draw balance, status, role; table of WalletService.get_ledger(user_id)
  on_deposit: TRY WalletService.deposit(session, amount_entry); render()
              EXCEPT ValueError: banner("Enter a valid amount")
ChatScreen.on_send() -> None
  append user bubble(question); disable Send
  resp <- ChatbotService.ask(session, question)           // run in worker thread; GUI stays
      responsive
  append bot bubble(resp.text, label = {RAG: "Store data", GENERAL: "General AI",
      ADMIN: "Admin data"}[resp.source])
  enable Send
CompanionScreen.on_action(action) -> None
  TRY  out <- {summarize: summarize(state, state.chapter), explain: explain(state,
      text_widget.selection),
              define: define(state, selected_word), quiz: quiz(state, state.chapter),
              ask: ask(state, entry)}[action]
       show out in side panel (quiz: radio buttons, reveal answers on Check)
  EXCEPT CompanionError e: banner(e.message)
AdminScreens: on_add_book() / on_taboo_*() / on_reopen(uid) / show_lists() ->
None
  on_add_book: TRY AdminService.add_book(session, form, cover, text); refresh table
               EXCEPT ValidationError e: outline e.problems
  on_taboo_add/edit/delete: TabooService.add_word / update_word / remove_word; refresh table
  on_reopen(uid): TRY AdminService.reopen_account(session,
      uid) EXCEPT ReopenError e: banner(e)
                  refresh AdminService.list_suspended(session)
  show_lists:  draw RatingService.get_list("NO_ORDER") and get_list("TO_ORDER");
               "Recalculate all" button -> RatingService.recalculate_all()

<!-- page 78 -->

# 5. System Screens

All screens share one layout: a navy sidebar whose items depend on the role
(MainWindow.build_sidebar) and a content area. Table 12 maps the major screens to roles and use
cases. Figures 27-32 are the Phase I mockups (the visual target); Figures 33-35 are new Tkinter
layout prototypes for screens the mockups did not cover; Section 5.2 is the working prototype.
*Table 12: Major screens*
Screen Roles Use cases Figure
Home (popular / recommended) VS, SU / RC, VC UC-03, UC-06 27, 28, 29
Sign In (face / voice) RC, VC, SU UC-02 33
Register VS UC-01 same layout as 33 + form fields
Browse / Search results All UC-04 27 (search bar, camera icon)
Book Details + Reviews All (buttons by role) UC-05, UC-08, UC-09, UC-10, UC-11 30, 36-39
My Balance (wallet + ledger) RC, VC (also suspended) UC-07 34
AI Chatbot All UC-12, UC-13 31
Smart Reading Companion RC, VC UC-14 35
Manage Books / Taboo Words SU UC-15, UC-16 32
User Management / Reports SU UC-17, UC-18 same table layout as 32

<!-- page 79 -->

## 5.1 Major GUI Screens

*Figure 27: Visitor home: search (text and cover image) and Top 3 Most Popular Books*

<!-- page 80 -->
*Figure 28: Registered Customer home: Recommended for You, balance and recent activity*

<!-- page 81 -->
*Figure 29: VIP Customer home: VIP banner and benefits, recommendations, balance*

<!-- page 82 -->
*Figure 30: Book Details: price, Add to Cart / Buy Now, reviews*

<!-- page 83 -->
*Figure 31: AI Chatbot: answers with book suggestions from store data*

<!-- page 84 -->
*Figure 32: Super-User: Book Catalog Management and Taboo Word Management*

<!-- page 85 -->
*Figure 33: Sign In (layout prototype): username, Face / Voice tabs, live camera frame, attempt counter*
*Figure 34: My Balance (layout prototype): balance, Add Funds, ledger of deposits, purchases and fines*

<!-- page 86 -->
*Figure 35: Smart Reading Companion (layout prototype): chapter text with selection, AI actions, answer panel*

## 5.2 Prototype: Submit Review with Taboo Moderation

We prototyped UC-10 Submit Book Reviews together with UC-11 Receive Review Warnings,
because this one action exercises the most rules: masking (R9), blocking and warnings (R9, R10),
VIP demotion and RC suspension (R10), weighted ratings (R12) and the order lists (R13). The
prototype is real code, not a mock-up: the Tkinter screen calls ReviewService, ModerationEngine,
WarningService, StatusManager and RatingService exactly as specified in Section 4, and
everything is stored in JSON Lines text files.
How to run (from the repository root):
cd prototype
python seed.py                     # resets data/ with 4 users, 3 books, 3 reviews,
    7 taboo words
python app.py                      # opens the Book Details / Write a review screen
python -m unittest tests.test_reviews -v
The Signed in as list in the header stands in for biometric sign-in in this prototype. The demo data:
Selina Zhu is a VIP who bought Dune; Evan Florentino is an RC who already has 2 warnings.
Scenario 1 - normal (masked review). Selina gives 4 stars with one taboo word. The word is
replaced by asterisks, the review is published with weight 2.0 (verified buyer), and the 4th rating
moves Dune onto the To-Order List (weighted average 4.57 > 4 with more than 3 ratings).

<!-- page 87 -->
*Figure 36: Prototype - VIP customer writes a review containing one taboo word*
*Figure 37: Prototype - review published with the word masked; book added to the To-Order List*
Scenario 2 - exceptional (blocked, RC suspended). Evan's comment contains 4 taboo words. It is
blocked, a 3rd warning is issued and, because an RC with more than 2 warnings is suspended, his
account becomes SUSPENDED and the form is disabled.

<!-- page 88 -->
*Figure 38: Prototype - comment blocked, third warning, Registered Customer suspended*
Scenario 3 - exceptional (blocked, VIP demoted). Selina posts a comment with 4 taboo words. It
is blocked, she gets her first warning and loses VIP status; the price shown immediately returns to
the full $14.99 and the header now shows (RC).
*Figure 39: Prototype - comment blocked, VIP Customer demoted to Registered Customer*
The status changes written by the prototype to data/status_changes.txt:

<!-- page 89 -->
{"change_id":"SC-0001","user_id":"U-
0002","from_role":"RC","to_role":"RC","from_status":"ACTIVE",
 "to_status":"SUSPENDED","reason":"3 warnings","timestamp":"2026-11-15 00:53:16"}
{"change_id":"SC-0002","user_id":"U-
0001","from_role":"VC","to_role":"RC","from_status":"ACTIVE",
 "to_status":"ACTIVE","reason":"blocked comment","timestamp":"2026-11-15 00:53:18"}
*Table 13: Prototype unit tests (6 of 6 pass)*
Unit test Rule checked Result
test_mask_up_to_three R9: 3 taboo words (mixed case) masked letter-for-letter, review published Pass
test_block_and_suspend_rc_on_third_war
ning
R9, R10: 4 taboo words blocked; RC with 2 prior warnings
suspended Pass
test_vip_demoted_after_one_blocked_com
ment R10: VC demoted to RC; promotion counters reset to 0 Pass
test_suspended_user_cannot_review R8: suspended account cannot submit Pass
test_weighted_average_and_to_order R12, R13: verified rating counts x2; average > 4 with > 3 ratings -> To-Order Pass
test_no_order R13: average < 2 with > 3 ratings -> No-Order Pass

<!-- page 90 -->

# 6. Group Meeting Memos and Team Concerns

Dates, attendance and owners in [brackets] are to be filled in by the team before submission.
Memo 1 - Phase I feedback and Phase II plan
Date Attendees Location / duration
[date, time] [attendees] [location, minutes]
Discussed
- Reviewed the Phase I grade (90) and comment: the use-case diagram had 18 use cases but
only 8 were described.
- Found two conflicting VIP demotion rules in the Phase I text.
Decided
- Phase II will describe all 18 use cases one by one, each with normal and exceptional
scenarios and its own diagram.
- A VIP is demoted after one blocked comment; an RC is suspended on the 3rd warning. All
rules are collected in one table (Table 2) that everyone uses.
- Visitors may use the chatbot for store questions only.
Action items
- Use cases UC-01 to UC-06: [owner]
- UC-07 to UC-12: [owner]
- UC-13 to UC-18: [owner]
- E-R diagram: [owner]
- Pseudo-code: split by class, [owners]
Memo 2 - Data design
Date Attendees Location / duration
[date, time] [attendees] [location, minutes]
Discussed
- How to store data in text files without a database, and how to avoid corrupt files.
Decided
- One JSON object per line, one file per entity (15 files); IDs with prefixes (U-, B-, R-...).
- Only the FileStore class touches files; full rewrites use a temporary file and an atomic rename.
- Every money change goes through a ledger transaction; every role/status change is logged.
- Store biometric embeddings (.npy), never the raw photos or recordings.
Action items
- Write FileStore and seed script: [owner]
- Draw E-R diagram and data dictionary: [owner]

<!-- page 91 -->
Memo 3 - AI components
Date Attendees Location / duration
[date, time] [attendees] [location, minutes]
Discussed
- Face recognition approach, LLM choice, chatbot permissions and the Reading Companion.
Decided
- YOLO detects the face; an embedding model compares faces, so new users need no
retraining. Voice (Resemblyzer) is the backup method.
- Ollama with llama3.2:3b for answers and nomic-embed-text for retrieval; fall back to
llama3.2:1b on laptops with little memory.
- The chatbot never lets the LLM invent admin numbers: they are computed from files first.
- The Reading Companion answers only from the book's own text (retrieval per book and
chapter).
Action items
- Test Ollama on every member's laptop: [all]
- Collect 10 Gutenberg books with covers: [owner]
Memo 4 - Prototype and report review
Date Attendees Location / duration
[date, time] [attendees] [location, minutes]
Discussed
- Demo of the review-moderation prototype; review of the full report draft.
Decided
- Prototype accepted: 3 scenarios work and 6 unit tests pass.
- Repository structure agreed (Section 7); the report and all diagrams go into docs/.
Action items
- Final proofreading: [owner]
- Upload report to the 322 portal by Nov. 24, 11:59 pm: [owner]

## 6.1 Possible Concerns of Team Work

*Table 14: Team-work concerns and mitigations*
Concern Risk What we will do
Uneven workload among five
members
Some parts late or
inconsistent
GitHub Issues with one owner per task; short weekly
check-in; every pull request reviewed by another
member.
Rules drifting between
members
Different code paths apply
different thresholds
Rules live only in Table 2 and as named constants in
one rules.py; unit tests for each rule.

<!-- page 92 -->
Concern Risk What we will do
Merge conflicts in data files Lost test data, broken JSON lines data/ is in .gitignore; everyone recreates it with seed.py.
Different laptops (no webcam,
no GPU, little RAM)
Biometrics or the LLM cannot
run for some members
Voice login as fallback; small Ollama model; AI calls
behind classes that can be replaced by simple stubs
for testing.
Large AI libraries (PyTorch,
Ultralytics, OpenCLIP) Long installs, version conflicts Pinned requirements.txt, one shared setup guide, integrate the AI parts early rather than in the last week.
Two copies of the app writing
the same files Lost updates A lock file at start-up allows only one running instance per data folder.
Privacy of biometric data Face data leaked in the repository Only embeddings stored; data/biometrics/ never committed.
Schedule pressure before the
final demo Unfinished features Build in order of the use-case table; each use case merged only when its scenarios work.

<!-- page 93 -->

# 7. Git Repository

Repository address: [https://github.com/<team-account>/BookOrbit-AI] (to be filled in by the team).
All materials, including this report, are kept in the repository:
BookOrbit-AI/
|-- README.md                 setup and run instructions
|-- requirements.txt          pinned Python packages
|-- docs/
|   |-- Phase1_Specification.pdf
|   |-- Phase2_Design_Report.docx      (this report)
|   `-- diagrams/                       collaboration, sequence,
    Petri net and E-R sources (.dot / .py) and images
|-- prototype/                Section 5.2 prototype
|   |-- app.py                Book Details / Write a review screen (Tkinter)
|   |-- screens_extra.py      Sign In, My Balance, Reading Companion layouts
|   |-- seed.py               creates demo data in data/
|   |-- bookorbit/
|   |   |-- filestore.py      FileStore (JSON Lines text files)
|   |   `-- reviews.py        ReviewService, ModerationEngine, WarningService, StatusManager,
    RatingService
|   `-- tests/test_reviews.py 6 unit tests
`-- data/                     created at run time, not committed (.gitignore)