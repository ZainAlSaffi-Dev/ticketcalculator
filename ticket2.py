"""UQCS event ticket calculator.  Run with:  streamlit run ticket2.py

Money model (see README §8-9):
  net revenue per ticket = price × (1 − refund) × (1 − platform fee)
  costs                  = fixed costs (incl. catering) + merch per show-up
  UQCS spend             = costs − net revenue   (negative = surplus)
"""
import pandas as pd

ROUND_COLS = ["Round", "Price", "Tickets", "Merch"]


# ──────────── Pure calculations (tested in test_ticket2.py) ────────────

def clean_rounds(rounds: pd.DataFrame) -> pd.DataFrame:
    """Drop half-filled editor rows and coerce types."""
    df = rounds.dropna(subset=["Price", "Tickets"]).copy()
    df["Round"] = df["Round"].fillna("").astype(str)
    df["Merch"] = df["Merch"].fillna(False).astype(bool)
    return df.reset_index(drop=True)


def make_rounds(first_price, step, n, total) -> pd.DataFrame:
    """n rounds rising by `step`; tickets spread evenly, remainder to the earliest rounds."""
    n, total = int(n), int(total)
    return pd.DataFrame([[f"Round {i + 1}", first_price + i * step, total // n + (i < total % n), False]
                         for i in range(n)], columns=ROUND_COLS)


def round_table(rounds, refund, fee, merch_unit) -> pd.DataFrame:
    df = clean_rounds(rounds)
    df["Gross sales"] = df["Price"] * df["Tickets"]
    df["Refunds"] = df["Gross sales"] * refund
    df["Platform fees"] = (df["Gross sales"] - df["Refunds"]) * fee
    df["Net revenue"] = df["Gross sales"] - df["Refunds"] - df["Platform fees"]
    df["Merch cost"] = df["Merch"] * df["Tickets"] * (1 - refund) * merch_unit
    df["Running total"] = (df["Net revenue"] - df["Merch cost"]).cumsum()
    return df


def summary(table: pd.DataFrame, fixed_costs: float) -> dict:
    costs = fixed_costs + table["Merch cost"].sum()
    revenue = table["Net revenue"].sum()
    return {"costs": costs, "revenue": revenue, "uqcs_spend": costs - revenue}


def break_even_shift(rounds, fixed_costs, contribution, refund, fee, merch_unit) -> float:
    """$ to add to every round price so that spend == contribution (keeps round steps)."""
    t = round_table(rounds, refund, fee, merch_unit)
    k = (1 - refund) * (1 - fee)
    tickets = t["Tickets"].sum()
    if tickets <= 0 or k <= 0:
        return float("nan")
    gap = fixed_costs + t["Merch cost"].sum() - contribution - t["Net revenue"].sum()
    return gap / (k * tickets)


def split_between_clubs(amount: float, clubs: pd.DataFrame, mode: str):
    """Clubs with a Fixed pledge pay exactly that; the rest is split (even or by attendees)
    between the others, capping anyone at their Max and pushing the excess onto the rest.
    Returns (table, leftover): leftover > 0 = nobody left to cover it, < 0 = pledges exceed gap."""
    df = clubs.dropna(subset=["Club"]).reset_index(drop=True)
    df = df.assign(**{c: pd.to_numeric(df[c], errors="coerce") for c in ("Attendees", "Fixed", "Max")})
    by_att = mode == "By attendees" and df["Attendees"].fillna(0).sum() > 0
    weights = df["Attendees"].fillna(0) if by_att else pd.Series(1.0, index=df.index)
    df["Amount"], df["How"], df["Share %"] = 0.0, "", 0.0
    if df.empty:
        return df, amount
    if amount <= 0:  # surplus: hand it back by weight, pledges/caps don't apply
        df["Share %"] = 100 * weights / weights.sum()
        df["Amount"], df["How"] = amount * df["Share %"] / 100, "share of surplus"
        return df, 0.0

    fixed = df["Fixed"].notna()
    df.loc[fixed, "Amount"], df.loc[fixed, "How"] = df.loc[fixed, "Fixed"], "fixed pledge"
    left = amount - df["Amount"].sum()
    active = ~fixed
    while left > 1e-9 and active.any() and weights[active].sum() > 0:
        share = left * weights[active] / weights[active].sum()
        over = share > df.loc[active, "Max"]  # NaN max → never over
        if not over.any():
            df.loc[active, "Amount"] = share
            df.loc[active, "How"] = "split by attendees" if by_att else "even split"
            left = 0.0
            break
        hit = over[over].index
        df.loc[hit, "Amount"], df.loc[hit, "How"] = df.loc[hit, "Max"], "capped at max"
        left -= df.loc[hit, "Max"].sum()
        active[hit] = False
    df["Share %"] = df["Amount"] / amount * 100
    return df, left


def plain_clubs(split: pd.DataFrame) -> pd.DataFrame:
    """Clubs with no Fixed or Max — in an even split they all pay the same."""
    return split[split["Fixed"].isna() & split["Max"].isna()]


def contributions_by_price(rounds, fixed_costs, clubs, mode, refund, fee, merch_unit, step=5.0):
    """One row per price level (every round moved by the same $ step): the shortfall and
    what each club pays. In an even split the no-limit clubs collapse into one column."""
    base = clean_rounds(rounds)
    rows = []
    for i in range(-2, 5):
        d = i * step
        if (base["Price"] + d < 0).any():
            continue
        shifted = base.assign(Price=base["Price"] + d)
        gap = summary(round_table(shifted, refund, fee, merch_unit), fixed_costs)["uqcs_spend"]
        split, left = split_between_clubs(gap, clubs, mode)
        plain = plain_clubs(split) if mode == "Even" else split.iloc[:0]
        row = {"Price change": "now" if d == 0 else f"{'+' if d > 0 else '−'}{money(abs(d))}",
               "Round prices": " / ".join(money(p) for p in shifted["Price"]),
               "Shortfall": gap}
        if len(plain):
            row[f"Each other club (×{len(plain)})"] = plain["Amount"].iloc[0]
        for _, c in split.drop(plain.index).iterrows():
            row[c["Club"]] = c["Amount"]
        row["Uncovered"] = max(left, 0.0)
        rows.append(row)
    return pd.DataFrame(rows)


# ──────────── UI ────────────

def money(x):
    x = round(float(x), 2) + 0.0  # avoid "-$0.00"
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


def md(x):  # money() escaped so Streamlit markdown doesn't treat $…$ as LaTeX
    return money(x).replace("$", r"\$")


def cost_editor(key, defaults):
    import streamlit as st
    st.markdown("**💸 Costs** — anything you pay for regardless of how many tickets sell")
    df = st.data_editor(
        pd.DataFrame(defaults, columns=["Item", "Cost"]), key=f"{key}_costs",
        num_rows="dynamic", width="stretch", hide_index=True,
        column_config={"Item": st.column_config.TextColumn("Cost item"),
                       "Cost": st.column_config.NumberColumn("Cost ($)", min_value=0.0, format="$%.2f")})
    return float(df["Cost"].fillna(0).sum())


PRICING_MODES = ["Single price", "Increasing rounds", "Custom tiers"]


def round_columns():
    import streamlit as st
    return {
        "Round": st.column_config.TextColumn("Round / tier name"),
        "Price": st.column_config.NumberColumn("Ticket price ($)", min_value=0.0, format="$%.2f",
                                               help="Price shown on the ticket site"),
        "Tickets": st.column_config.NumberColumn("Tickets expected", min_value=0, step=1),
        "Merch": st.column_config.CheckboxColumn("Includes merch?", default=False,
                                                 help="Tick if this ticket comes with a shirt etc."),
    }


def rounds_editor(key, tiers, mode="Increasing rounds", price=15.0, step=5.0, n=3, total=100):
    """Ticket input in one of three shapes; always returns a ROUND_COLS DataFrame."""
    import streamlit as st
    st.markdown("**🎟️ Tickets**")
    mode = st.radio("How are tickets priced?", PRICING_MODES, index=PRICING_MODES.index(mode),
                    horizontal=True, key=f"{key}_mode",
                    help="Single price: one price for everyone. Increasing rounds: e.g. $15 → $20 → $25. "
                         "Custom tiers: any mix of ticket types (early bird, merch bundles…).")
    if mode == "Single price":
        a, b, c = st.columns([2, 2, 1])
        p = a.number_input("Ticket price ($)", min_value=0.0, value=price, step=1.0, key=f"{key}_p")
        t = b.number_input("Tickets expected", min_value=0, value=total, step=5, key=f"{key}_t")
        m = c.checkbox("Includes merch", key=f"{key}_m")
        return pd.DataFrame([["Single price", p, t, m]], columns=ROUND_COLS)

    if mode == "Increasing rounds":
        a, b, c, d = st.columns(4)
        p = a.number_input("Round 1 price ($)", min_value=0.0, value=price, step=1.0, key=f"{key}_rp")
        sp = b.number_input("Increase per round ($)", min_value=0.0, value=step, step=1.0, key=f"{key}_rs")
        rn = c.number_input("Number of rounds", min_value=1, max_value=10, value=n, key=f"{key}_rn")
        t = d.number_input("Total tickets", min_value=0, value=total, step=5, key=f"{key}_rt")
        st.caption("Tickets are spread evenly across rounds — edit the table to tweak any round.")
        return st.data_editor(make_rounds(p, sp, rn, t), key=f"{key}_gen_{p}_{sp}_{rn}_{t}",
                              num_rows="fixed", width="stretch", hide_index=True,
                              column_config=round_columns())

    st.caption("One row per ticket type — add or delete rows as needed.")
    return st.data_editor(pd.DataFrame(tiers, columns=ROUND_COLS), key=f"{key}_rounds",
                          num_rows="dynamic", width="stretch", hide_index=True,
                          column_config=round_columns())


def show_results(key, rounds, fixed_costs, refund, fee, merch_unit, contribution_label, who="UQCS",
                 contribution=None):
    """contribution=None asks for it with an input; otherwise uses the given amount."""
    import streamlit as st
    if contribution is None:
        contribution = st.number_input(
            contribution_label, min_value=0.0, value=0.0, step=100.0, key=f"{key}_contrib",
            help="Used for the 'Break-even price' column: prices where this amount exactly covers the gap.")

    table = round_table(rounds, refund, fee, merch_unit)
    if table.empty:
        st.warning("Add at least one ticket round with a price and ticket count.")
        return None
    s = summary(table, fixed_costs)
    delta = break_even_shift(rounds, fixed_costs, contribution, refund, fee, merch_unit)
    table["Break-even price"] = table["Price"] + delta

    st.markdown("### 📈 Results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total costs", money(s["costs"]), help="Fixed costs + merch for attendees who show up")
    c2.metric("Ticket revenue we keep", money(s["revenue"]), help="After refunds and platform fees")
    c3.metric("Tickets sold", f"{int(table['Tickets'].sum()):,}")
    pay = "pays" if who == "UQCS" else "pay"
    if s["uqcs_spend"] > 0:
        c4.metric(f"Shortfall — {who} {pay}", money(s["uqcs_spend"]), delta="loss", delta_color="inverse")
    else:
        c4.metric(f"Surplus — {who} keeps", money(-s["uqcs_spend"]), delta="surplus")

    shift_txt = ('+' if delta >= 0 else '−') + md(abs(delta))
    if len(table) == 1:
        st.caption(f"**Break-even ticket price: {md(table['Price'][0] + delta)}** "
                   f"(so {who} contribute exactly {md(contribution)}).")
    else:
        st.caption(f"**Break-even price** = each round's price {shift_txt}, so {who} contribute exactly "
                   f"{md(contribution)}. Round-to-round price steps are kept.")
    st.dataframe(
        table.drop(columns=["Merch"]), hide_index=True, width="stretch",
        column_config={c: st.column_config.NumberColumn(c, format="$%.2f") for c in
                       ["Price", "Gross sales", "Refunds", "Platform fees", "Net revenue",
                        "Merch cost", "Running total", "Break-even price"]}
        | {"Round": "Round / tier", "Tickets": "Tickets"})

    with st.expander(f"Break-even prices if {who} contribute more…"):
        rows = {}
        for amt in [0, 500, 1000, 2000, 3000]:
            d = break_even_shift(rounds, fixed_costs, amt, refund, fee, merch_unit)
            rows[f"{who} contribute {money(amt)}"] = (table["Price"] + d).map(money).tolist()
        st.dataframe(pd.DataFrame(rows, index=table["Round"]).T, width="stretch")
    return s


def main():
    import streamlit as st
    st.set_page_config(layout="wide", page_title="UQCS Ticket Calculator")
    st.title("🎟️ UQCS Ticket Calculator")
    st.write("Enter costs and ticket rounds → see how much UQCS spends, and what prices break even.")

    with st.sidebar:
        st.header("⚙️ Assumptions")
        refund = st.slider("Refund rate (%)", 0, 20, 3, help="Share of tickets expected to be refunded") / 100
        fee = st.slider("Platform fee (%)", 0, 20, 4, help="Humanitix etc. fee as % of ticket price") / 100
        merch_unit = st.number_input("Merch cost per unit ($)", min_value=0.0, value=20.0, step=1.0)

    hack, standard, collab, how = st.tabs(
        ["🏆 Hackathon", "🎤 Standard event", "🤝 Collab event", "ℹ️ How it works"])

    with hack:
        st.subheader("Hackathon — prizes, catering, merch")
        left, right = st.columns(2)
        with left:
            fixed = cost_editor("hack", [["Prizes", 3000.0], ["Venue / AV", 1000.0], ["Misc", 500.0]])
        with right:
            st.markdown("**🍕 Catering** — total = $/meal × meals × attendees")
            a, b, c = st.columns(3)
            per_meal = a.number_input("$ per meal per person", min_value=0.0, value=8.0, step=0.5)
            meals = b.number_input("Meal occasions", min_value=0, value=5, step=1,
                                   help="e.g. Fri dinner, Sat breakfast/lunch/dinner, Sun breakfast")
            heads = c.number_input("Attendees fed", min_value=0, value=167, step=5)
            catering = per_meal * meals * heads
            st.info(f"Catering total: **{md(catering)}** · fixed costs incl. catering: "
                    f"**{md(fixed + catering)}**")
        rounds = rounds_editor("hack", mode="Custom tiers", price=45.0, total=167, tiers=[  # 2024 tiers
            ["Early Bird + Shirt (UQ)", 55.0, 51, True], ["Early Bird (UQ)", 35.0, 86, False],
            ["UQ Regular", 45.0, 14, False], ["Early Bird (Non-UQ)", 40.0, 9, False],
            ["Early Bird + Shirt (Non-UQ)", 60.0, 4, True], ["Non-UQ", 50.0, 3, False]])
        show_results("hack", rounds, fixed + catering, refund, fee, merch_unit,
                     "UQCS / sponsor money to put in ($)")

    with standard:
        st.subheader("Standard event — networking, socials, smaller events")
        left, right = st.columns(2)
        with left:
            fixed = cost_editor("std", [["Venue + food", 1500.0]])
        with right:
            rounds = rounds_editor("std", [["Round 1", 15.0, 40, False], ["Round 2", 20.0, 40, False],
                                           ["Round 3", 25.0, 20, False]])
        show_results("std", rounds, fixed, refund, fee, merch_unit, "UQCS money to put in ($)")

    with collab:
        st.subheader("Collab event — costs shared with other clubs")
        left, right = st.columns(2)
        with left:
            fixed = cost_editor("col", [["Venue", 3000.0], ["Food & drinks", 4000.0]])
            st.markdown("**🤝 Clubs involved**")
            n = int(st.number_input("Number of clubs (incl. UQCS)", min_value=1, max_value=50, value=2))
            st.caption("Leave the table blank for a plain split. Fill **Fixed** for a club pledging an exact "
                       "amount, **Max** for a club that can only put in so much — the rest is split between "
                       "everyone else. Attendees only matter for the 'By attendees' split.")
            saved = st.session_state.get("col_clubs_saved")
            default = pd.DataFrame({"Club": ["UQCS"] + [f"Club {i}" for i in range(2, n + 1)],
                                    "Attendees": [None] * n, "Fixed": [None] * n, "Max": [None] * n})
            if saved is not None:  # keep earlier edits when the club count changes
                keep = saved.head(n).reset_index(drop=True)
                default.iloc[:len(keep)] = keep.values
            default = default.astype({"Attendees": float, "Fixed": float, "Max": float})
            clubs = st.data_editor(
                default, key=f"col_clubs_{n}", num_rows="fixed", width="stretch", hide_index=True,
                column_config={
                    "Club": st.column_config.TextColumn("Club"),
                    "Attendees": st.column_config.NumberColumn("Attendees", min_value=0, format="%d"),
                    "Fixed": st.column_config.NumberColumn("Fixed ($)", min_value=0.0, format="$%.2f",
                                                           help="Pays exactly this, e.g. UQCS commits $1,000"),
                    "Max": st.column_config.NumberColumn("Max ($)", min_value=0.0, format="$%.2f",
                                                         help="Never pays more than this"),
                })
            st.session_state["col_clubs_saved"] = clubs
            mode = st.radio("How to split the rest", ["Even", "By attendees"], horizontal=True,
                            help="Usually even; use 'By attendees' for balls etc.")
        with right:
            rounds = rounds_editor("col", [["Round 1", 15.0, 50, False], ["Round 2", 20.0, 50, False],
                                           ["Round 3", 25.0, 30, False]], total=130)
        pledged = float(pd.to_numeric(clubs["Fixed"], errors="coerce").fillna(0).sum())
        s = show_results("col", rounds, fixed, refund, fee, merch_unit, None, who="Clubs",
                         contribution=pledged)
        if s:
            gap = s["uqcs_spend"]
            split, leftover = split_between_clubs(gap, clubs, mode)
            plain = plain_clubs(split)
            st.markdown("### 🧾 What each club contributes at these ticket prices")
            if gap > 0:
                fixed_amt = split.loc[split["How"] == "fixed pledge", "Amount"].sum()
                capped_amt = split.loc[split["How"] == "capped at max", "Amount"].sum()
                n_split = int((split["How"].isin(["even split", "split by attendees"])).sum())
                rest = gap - fixed_amt - capped_amt
                lines = [("Total costs", s["costs"]),
                         ("− Ticket revenue we keep (after refunds & fees)", -s["revenue"]),
                         ("**= Shortfall**", gap)]
                if fixed_amt:
                    lines.append(("− Fixed pledges", -fixed_amt))
                if capped_amt:
                    lines.append(("− Clubs capped at their max", -capped_amt))
                lines.append((f"**= Left to split between {n_split} club{'s' * (n_split != 1)}**",
                              max(rest, 0)))
                if mode == "Even" and len(plain):
                    lines.append(("**÷ each of those clubs pays**", plain["Amount"].iloc[0]))
                if leftover > 0.005:
                    lines.append(("⚠️ Uncovered", leftover))
                st.markdown("| How it adds up | |\n|---|---:|\n" +
                            "\n".join(f"| {k} | {md(v)} |" for k, v in lines))
            else:
                st.success(f"Ticket revenue covers all costs with {md(-gap)} to spare — "
                           "no club needs to contribute (surplus split below).")
            split = split[["Club", "How", "Share %", "Amount"]]
            st.dataframe(split, hide_index=True, width="stretch", column_config={
                "How": "How it was worked out",
                "Share %": st.column_config.NumberColumn(format="%.1f%%"),
                "Amount": st.column_config.NumberColumn("Pays (+) / receives (−)", format="$%.2f")})
            if leftover > 0.005:
                st.error(f"{md(leftover)} still uncovered — every club is at its fixed amount or max. "
                         "Raise a max, add a club, or raise ticket prices.")
            elif leftover < -0.005:
                st.warning(f"Fixed pledges are {md(-leftover)} more than the shortfall — "
                           "someone could pledge less.")

            st.markdown("### 📊 Club contributions at different ticket prices")
            st.caption("Every round's price moves up or down by the same step. If the per-club number "
                       "at 'now' is too high, pick the row where it's one everyone can live with.")
            step = st.number_input("Price step ($)", min_value=0.5, value=5.0, step=0.5, key="col_step")
            grid = contributions_by_price(rounds, fixed, clubs, mode, refund, fee, merch_unit, step)
            st.dataframe(grid, hide_index=True, width="stretch", column_config={
                c: st.column_config.NumberColumn(c, format="$%.2f")
                for c in grid.columns if c not in ("Price change", "Round prices")})

    with how:
        st.markdown("""
| Column | Meaning |
|---|---|
| **Gross sales** | price × tickets — what buyers pay |
| **Refunds** | gross × refund rate |
| **Platform fees** | (gross − refunds) × platform fee |
| **Net revenue** | what actually lands in the bank |
| **Merch cost** | merch unit cost × tickets with merch who show up |
| **Running total** | cumulative net revenue − merch after each round |
| **Break-even price** | every round shifted by the same $ so the money put in exactly covers the gap |

**UQCS spends** = fixed costs + catering + merch − net revenue. Negative means a surplus.

Catering is treated as a fixed total (food is ordered up front; refunds don't save it).

**Break-even shift** Δ = (costs − contribution − net revenue) ÷ ((1 − refund)(1 − fee) × total tickets).
""")


if __name__ == "__main__":
    main()
