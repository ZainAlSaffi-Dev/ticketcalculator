# Ticket-Pricing Reference Implementation


*The first half derives the break-even formula step-by-step.*  
*The second half maps every symbol to the Python functions in
`ticket2.py`.*

## 0 Running frontend ticket2.py

```bash
streamlit run ticket2.py
```

Tabs: **Hackathon** (prizes, catering, merch tiers), **Standard event**
(networking/smaller events), **Collab event** (splits the shortfall evenly or
by attendees between clubs). Every tab takes ticket rounds (e.g. $15 → $20 → $25)
and shows how much UQCS spends plus the break-even price for each round.

Self-check for the maths:

```bash
python3 test_ticket2.py
```

---

## 1  Declare (then fill-in) your inputs

| Symbol | What **you** type in | Where it normally comes from |
|--------|----------------------|------------------------------|
| `F`    | **total** fixed costs | venue, AV, insurance, marketing |
| `v`    | variable cost **per attendee** | catering ÷ head-count, plus optional merch |
| `S`    | sponsorship / grants already locked in | signed agreements |
| `φ`    | refund rate (0 – 1) | past events or policy |
| `c_ref`| payment-processor refund fee | Stripe, PayPal schedule |
| `Q(P)` | demand curve – expected sales at price `P` | old ticket data or a survey |
| `P`    | ticket price you’re solving for | – |

---

## 2  Choose a demand curve

Most clubs start with a **linear** curve:

$$
Q(P)=a-bP
$$

* `a` = intercept (tickets if it were free)  
* `b` = slope (tickets lost per \$1 price rise)  
  `dQ/dP = –b` is constant.

If you prefer, swap in a constant-elasticity form

$$
Q(P)=A\,P^{-\varepsilon},\quad \varepsilon>0
$$


---

## 3  How many people actually show up?

Only a fraction `(1 − φ)` keep their ticket:

$$
\tilde Q(P)=(1-\phi)\,Q(P)
$$

---

## 4  Write the revenue-and-cost pieces

| Piece | Formula | Why |
|-------|---------|-----|
| Revenue kept | $(1-\phi)P\,Q(P)$ | refunds paid back |
| Fixed cost | $F$ | independent of head-count |
| Variable cost | $(1-\phi)v\,Q(P)$ | only show-ups consume |
| Refund fee | $c_{\text{ref}}\phi\,Q(P)$ | optional |
| Sponsorship | $S$ | offsets the gap |

---

## 5  Profit function

![alt text](image.png)






---

## 6  Break-even condition

Set $\pi(P)=0$ and drop the refund-fee term if you like:

$$
(1-\phi)\,(P-v)\,Q(P)=F-S
$$

Everything on the left depends on `P`; everything on the right is a
constant you **must** cover.

---

## 7  Insert the linear curve → quadratic

$$
(1-\phi)\,(a-bP)\,(P-v)=F-S
$$

Expand or feed into a spreadsheet’s quadratic solver.  
Pick the root that satisfies **both**

* $P>v$   (price covers per-head cost)  
* $Q(P)>0$ (positive demand).

---


## 8  Final constant-refund, single-tier formula (keep it!)

$$
(1-\phi)\,(P-v)\,Q(P)=F-S
$$

_Left-hand_: contribution per attendee × non-refunded attendees  
_Right-hand_: the fixed-cost gap that must be filled.

---

## 9  The ultra-simple shortcut (no demand curve)

If you **don’t** model demand (just assume `Q_est` tickets will be sold):

$$
P_{\text{net}} = v + \frac{F-S}{(1-\phi)\,Q_{\text{est}}}
$$

Add platform fee `f` to get the sticker price:

$$
P_{\text{gross}} = \frac{P_{\text{net}}}{1-f}.
$$

---

## 10  How the code mirrors the maths

| Python | Math symbol | Notes |
|--------|-------------|-------|
| sidebar *Refund rate* | φ | refund rate |
| sidebar *Platform fee* | f | ticket-site fee |
| cost table + catering | F | catering is a fixed total (ordered up front) |
| *contribution* input | S | UQCS / sponsor / club money put in |
| *Merch cost* column | part of `v` | merch unit × show-ups with merch |
| `round_table()` | $(1-φ)(1-f)P\,Q$ per round | gross → refunds → fees → net |
| `summary()` | $F + \text{merch} - \text{net}$ | what UQCS spends (negative = surplus) |
| `break_even_shift()` | Δ | same $ added to every round so profit = 0 after S |
| `split_between_clubs()` | – | even or attendee-weighted split of the shortfall |
