import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
from yahooquery import Ticker

st.title("Stock evaluator 📈")
st.text(
    "A dashboard to evaluate the potential of stocks based on their Discounted Cash Flow"
)


@st.cache_data
def get_sp500_tickers():
    tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    sp500 = tables[0]["Symbol"].tolist()
    sp500 = [symbol.replace(".", "-") for symbol in sp500]
    return sp500


@st.cache_data
def load_data(ticker_name):
    ticker = Ticker(ticker_name)

    income = ticker.income_statement()
    cashflow = ticker.cash_flow()
    balance = ticker.balance_sheet()
    estimates = ticker.earnings_trend[ticker_name]
    key_stats = ticker.key_stats[ticker_name]
    financial = ticker.financial_data[ticker_name]

    data = {
        "income": income,
        "cashflow": cashflow,
        "balance": balance,
        "estimates": estimates,
        "key_stats": key_stats,
        "financial": financial,
    }

    return data


ticker_names = get_sp500_tickers()

with st.sidebar:
    st.text("Parameters for DCF calculation")
    ticker_name = st.selectbox("Ticker", ticker_names)
    estimate_type = st.selectbox("Estimate type", ["low", "avg", "high"])

    required_return = (
        st.number_input("Required return (%)", min_value=1.0, max_value=100.0, step=1.0)
        / 100
    )
    perpetual_growth = (
        st.number_input("Perpetual growth (%)", min_value=1.0, max_value=30.0, step=0.5)
        / 100
    )
    safety_margin = (
        st.number_input(
            "Safety margin (%)",
            min_value=1.0,
            max_value=100.0,
            step=1.0,
        )
        / 100
    )
    roic = st.number_input("ROIC (%)", min_value=1.0, max_value=100.0, step=1.0) / 100

year_now = datetime.datetime.now().year

data_load_state = st.text("Loading data...")
data = load_data(ticker_name)
data_load_state.text("")

income = data["income"]
cols = ["asOfDate", "TotalRevenue", "NetIncome"]
inc = income[income["periodType"] == "12M"][cols]
inc.loc[:, "year"] = pd.to_datetime(inc["asOfDate"]).dt.year
inc = inc.set_index("year").sort_index().drop(columns=["asOfDate"])

cashflow = data["cashflow"]
cols = ["asOfDate", "NetIncome", "CapitalExpenditure", "OperatingCashFlow"]
cf = cashflow[cashflow["periodType"] == "12M"][cols]
cf.loc[:, "year"] = pd.to_datetime(cf["asOfDate"]).dt.year
cf = cf.set_index("year").sort_index().drop(columns=["asOfDate"])

balance = data["balance"]
bc = balance[balance["periodType"] == "12M"]
bc.loc[:, "year"] = pd.to_datetime(bc["asOfDate"]).dt.year
bc = bc.set_index("year").sort_index().drop(columns=["asOfDate"])


free_cashflow_to_equity = cf["OperatingCashFlow"] + cf["CapitalExpenditure"]

estimates = data["estimates"]
df = pd.DataFrame(estimates["trend"]).rename(columns={"endDate": "date"})
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date")
df = df[["revenueEstimate"]]
df = df["revenueEstimate"].apply(pd.Series)
df = df.resample("1Y").max()
df = df[estimate_type]
df.index.name = "year"
df.name = "TotalRevenue"
df = df.reset_index()
df["year"] = df["year"].dt.year
ests = df.set_index("year")["TotalRevenue"]

year_min = bc.index.min()
year_max = ests.index.max()

# calculate future revenue
df = ests.to_frame()
df.loc[:, "DiscountFactor"] = 1
df["DiscountFactor"] = df["DiscountFactor"].cumsum()
df["DiscountFactor"] = (1 + required_return) ** df["DiscountFactor"]
df["TotalRevenue"] = df["TotalRevenue"] / df["DiscountFactor"]
df = df["TotalRevenue"]
rev = pd.concat([inc["TotalRevenue"], df])


# calculate avg income margin
net_inc_margins = cf["NetIncome"] / rev
net_inc_margin_avg = net_inc_margins.dropna().mean()


# calculate free cash flow to net income
fcfe_to_net_inc = free_cashflow_to_equity / cf["NetIncome"]

net_inc = pd.concat([cf["NetIncome"], rev.loc[year_now:] * net_inc_margin_avg])
net_inc.name = "NetIncome"


fcte_to_net_income_avg = (free_cashflow_to_equity / net_inc).dropna().mean()
free_cashflow_year_max = net_inc.loc[year_max] * fcte_to_net_income_avg
term = (
    free_cashflow_year_max
    * (1 + perpetual_growth)
    / (required_return - perpetual_growth)
)


today_value = rev.loc[year_now] + term
today_value_after_net_debt = (
    today_value
    - bc.loc[year_now - 1, "TotalDebt"]
    - bc.loc[year_now - 1, "CashAndCashEquivalents"]
)

nshares = data["key_stats"]["sharesOutstanding"]
fair_price = round((today_value_after_net_debt / nshares) * (1 - safety_margin), 2)
current_price = data["financial"]["currentPrice"]

test_revenue = (
    inc["TotalRevenue"].loc[year_now - 1] - inc["TotalRevenue"].loc[year_min]
) > 0
test_net_income = (
    cf["NetIncome"].loc[year_now - 1] - cf["NetIncome"].loc[year_min]
) > 0
test_free_cashflow = (
    cf["OperatingCashFlow"].loc[year_now - 1] - cf["OperatingCashFlow"].loc[year_min]
) > 0
test_balancesheet = (bc["TotalAssets"] - bc["TotalLiabilitiesNetMinorityInterest"]).loc[
    year_now - 1
] > 0
# test_shares_outshanding = key_stats['outstandingShares'].loc[year-1] - nshares['outstandingShares'].loc[year_past]
test_roic = (
    inc["NetIncome"]
    / (
        bc["TotalAssets"]
        - (
            bc["TotalLiabilitiesNetMinorityInterest"]
            - bc["TotalNonCurrentLiabilitiesNetMinorityInterest"]
        )
    )
).mean() > roic

st.header("DCF")
st.write(f"Fair value: {fair_price}")
st.write(f"Current value: {current_price}")

tab1, tab2, tab3, tab4 = st.tabs(
    ["TotalRevenue", "NetIncome", "OperatingCashFlow", "BalanceSheet"]
)

with tab1:
    st.header("Total Revenue")
    fig = px.bar(inc["TotalRevenue"].reset_index(), x="year", y="TotalRevenue")
    st.plotly_chart(fig)

with tab2:
    st.header("Net Income")
    fig = px.bar(cf["NetIncome"].reset_index(), x="year", y="NetIncome")
    st.plotly_chart(fig)

with tab3:
    nm = "OperatingCashFlow"
    st.header(nm)
    fig = px.bar(cf[nm].reset_index(), x="year", y=nm)
    st.plotly_chart(fig)

with tab4:
    nm = "BalanceSheet"
    df = bc["TotalAssets"] - bc["TotalLiabilitiesNetMinorityInterest"]
    df.name = nm
    st.header(nm)
    fig = px.bar(df.reset_index(), x="year", y=nm)
    st.plotly_chart(fig)
