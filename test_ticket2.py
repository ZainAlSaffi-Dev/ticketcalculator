import pandas as pd
from ticket2 import (round_table, summary, break_even_shift, split_between_clubs,
                     contributions_by_price, make_rounds, ROUND_COLS)

rounds = pd.DataFrame([["R1", 15.0, 10, False], ["R2", 20.0, 10, True]], columns=ROUND_COLS)

# no fees/refunds: revenue = 150 + 200, merch = 10 × $20
t = round_table(rounds, 0, 0, 20)
s = summary(t, 500)
assert s["revenue"] == 350 and s["costs"] == 700 and s["uqcs_spend"] == 350

# break-even shift brings spend to the contribution, with real fees/refunds
for contrib in (0, 100):
    d = break_even_shift(rounds, 500, contrib, 0.03, 0.04, 20)
    shifted = rounds.assign(Price=rounds["Price"] + d)
    assert abs(summary(round_table(shifted, 0.03, 0.04, 20), 500)["uqcs_spend"] - contrib) < 1e-9

def amounts(clubs, amount, mode="Even"):
    df, left = split_between_clubs(amount, pd.DataFrame(clubs, columns=["Club", "Attendees", "Fixed", "Max"]), mode)
    return [round(a, 2) for a in df["Amount"]], round(left, 2)

N = None
assert amounts([["UQCS", 30, N, N], ["Other", 10, N, N]], 400) == ([200, 200], 0)
assert amounts([["UQCS", 30, N, N], ["Other", 10, N, N]], 400, "By attendees") == ([300, 100], 0)
# UQCS pledges 1000, B capped at 100, rest split between C and D: (3000-1000-100)/2
assert amounts([["UQCS", N, 1000, N], ["B", N, N, 100], ["C", N, N, N], ["D", N, N, N]], 3000) == \
    ([1000, 100, 950, 950], 0)
# everyone capped → leftover reported; pledge > gap → negative leftover
assert amounts([["A", N, N, 100], ["B", N, N, 100]], 500) == ([100, 100], 300)
assert amounts([["A", N, 600, N], ["B", N, N, N]], 500) == ([600, 0], -100)
# surplus handed back evenly
assert amounts([["A", N, 600, N], ["B", N, N, N]], -200) == ([-100, -100], 0)

# price grid: $10×10 tickets, $500 costs, UQCS pledges 100, B max 50, C & D split the rest
clubs = pd.DataFrame([["UQCS", N, 100, N], ["B", N, N, 50], ["C", N, N, N], ["D", N, N, N]],
                     columns=["Club", "Attendees", "Fixed", "Max"])
grid = contributions_by_price(pd.DataFrame([["R1", 10.0, 10, False]], columns=ROUND_COLS),
                              500, clubs, "Even", 0, 0, 0, step=5).set_index("Price change")
assert list(grid.index) == ["−$10.00", "−$5.00", "now", "+$5.00", "+$10.00", "+$15.00", "+$20.00"]
assert grid.loc["now", "Shortfall"] == 400 and grid.loc["now", "Each other club (×2)"] == 125
assert grid.loc["+$5.00", "Each other club (×2)"] == 100 and grid.loc["+$5.00", "B"] == 50

r = make_rounds(15, 5, 3, 100)
assert r["Price"].tolist() == [15, 20, 25] and r["Tickets"].tolist() == [34, 33, 33]

print("ok")
