import requests
import datetime
import streamlit as st
import pandas as pd

API_KEY = "XX"

st.title("Stock evaluator")


def calc_compound(principal, interest, n_compound_periods, years):
    return principal * (
        pow((1 + interest / n_compound_periods), n_compound_periods * years)
    )


@st.cache_data
def load_data(ticker):
    ticker = ticker.upper()
    base_url = "https://financialmodelingprep.com/api"

    url = f"{base_url}/v3/income-statement/{ticker}?limit=120&apikey={API_KEY}"
    r = requests.get(url)
    income = pd.DataFrame(r.json())

    url = f"{base_url}/v3/cash-flow-statement/{ticker}?limit=120&apikey={API_KEY}"
    r = requests.get(url)
    cashflow = pd.DataFrame(r.json())

    url = f"{base_url}/v3/balance-sheet-statement/{ticker}?limit=120&apikey={API_KEY}"
    r = requests.get(url)
    balance = pd.DataFrame(r.json())

    url = f"{base_url}/v3/analyst-estimates/{ticker}?limit=120&apikey={API_KEY}"
    r = requests.get(url)
    estimates = None
    if not "Error Message" in r.json():
        estimates = pd.DataFrame(r.json())

    shares = None
    if not "Error Message" in r.json():
        url = f"{base_url}/v4/shares_float?symbol={ticker}&apikey={API_KEY}"
        r = requests.get(url)
        shares = pd.DataFrame(r.json())

    data = {
        "income": income,
        "cashflow": cashflow,
        "balance": balance,
        "estimates": estimates,
        "shares": shares,
    }

    return data


with st.sidebar:
    ticker = st.selectbox("Ticker", ["AAPL", "MSFT"])
    years_past = st.number_input("Past years", min_value=1, max_value=5)
    years_future = st.number_input("Future years", min_value=1, max_value=5)
    perpetual_growth = (
        st.slider("Perpetual growth", min_value=0, max_value=100, step=5) / 100
    )
    safety_margin = st.slider("Safety margin", min_value=0, max_value=100, step=5) / 100
    required_return = (
        st.slider("Required return", min_value=0, max_value=100, step=5) / 100
    )
    roic = st.slider("ROIC", min_value=0, max_value=100, step=1) / 100

year_now = datetime.datetime.now().year
year_past = year_now - years_past
year_future = year_now + years_future

data_load_state = st.text("Loading data...")
data = load_data(ticker)
data_load_state.text("Done! (using st.cache_data)")

inc = data["income"][["date", "revenue", "netIncome"]]
inc.loc[:, "year"] = pd.to_datetime(inc["date"]).dt.year
inc = inc.set_index("year").sort_index().drop(columns=["date"])
inc = inc.loc[year_past:year_now]

bc = data["balance"].copy()
bc["year"] = pd.to_datetime(bc["date"]).dt.year
bc = bc.set_index("year").sort_index()
bc = bc.loc[year_past : year_now - 1]

cf = data["cashflow"].copy()
cf[["date", "netIncome", "capitalExpenditure", "operatingCashFlow"]]
cf.loc[:, "year"] = pd.to_datetime(cf["date"]).dt.year
cf = cf.set_index("year").sort_index().drop(columns=["date"])
cf = cf.loc[year_past:year_now]

free_cashflow_to_equity = cf["operatingCashFlow"] + cf["capitalExpenditure"]

ests = data["estimates"].copy()
cols = ["date", "estimatedRevenueAvg"]
ests = ests[cols]
ests.loc[:, "year"] = pd.to_datetime(ests["date"]).dt.year
ests = ests.set_index("year").sort_index().drop(columns=["date"])

df = ests.loc[year_now:]["estimatedRevenueAvg"]
df.name = "revenue"

rev = pd.concat([inc["revenue"], df])

growth_rate_avg = rev.pct_change().dropna().mean()

rng = list(range(year_past, year_future + 1))

rev = rev.reindex(rng)

y = ests.reset_index()["year"].max()

principal = ests.loc[ests.idxmax()]["estimatedRevenueAvg"].iloc[0]
vs = []
for i in range(years_future + 1):
    vs.append(calc_compound(principal, growth_rate_avg, 1, i + 1))

rev.loc[y:] = vs

net_inc_margins = cf["netIncome"] / rev
net_inc_margin_avg = net_inc_margins.dropna().mean()

fcfe_to_net_inc = free_cashflow_to_equity / cf["netIncome"]
fcfe_to_net_inc

net_inc = pd.concat([cf["netIncome"], rev.loc[y:] * net_inc_margin_avg])
net_inc.name = "net_income"

free_cashflow_to_equity = free_cashflow_to_equity.reindex(
    list(range(year_past, year_future + 1))
)
free_cashflow_to_equity.loc[y:year_future] = (
    net_inc.loc[y:year_future] * fcfe_to_net_inc.mean()
)

disf = net_inc.loc[y:year_future]
disf.loc[:] = 1
disf = disf.cumsum()
disf = (1 + required_return) ** disf

term = (
    free_cashflow_to_equity.loc[year_future]
    * (1 + perpetual_growth)
    / (required_return - perpetual_growth)
)

today_value = (free_cashflow_to_equity.loc[y:] / disf).sum() + (term / disf.max())

fair_value = today_value / data["shares"]

test_revenue = (inc["revenue"].loc[year_now - 1] - inc["revenue"].loc[year_past]) > 0
test_net_income = (
    cf["netIncome"].loc[year_now - 1] - cf["netIncome"].loc[year_past]
) > 0
test_free_cashflow = (
    cf["freeCashFlow"].loc[year_now - 1] - cf["freeCashFlow"].loc[year_past]
) > 0
test_balancesheet = (bc["totalAssets"] - bc["totalLiabilities"]).loc[year_now - 1] > 0
# test_shares_outshanding = nshares['outstandingShares'].loc[year-1] - nshares['outstandingShares'].loc[year_past]
test_roic = (
    inc["netIncome"] / (bc["totalAssets"] - bc["totalCurrentLiabilities"])
).mean() > roic

st.write(data)
