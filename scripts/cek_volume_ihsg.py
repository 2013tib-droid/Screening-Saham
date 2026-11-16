"""Pemeriksaan: apakah volume ^JKSE dari Yahoo terisi dan masuk akal?

Dicetak apa adanya ke log Actions. Tidak menulis berkas apa pun.
"""
import pandas as pd
import yfinance as yf

d = yf.Ticker("^JKSE").history(start="2023-10-01", interval="1d", auto_adjust=False)
d.index = d.index.tz_localize(None)
pd.set_option("display.width", 200)
print("Jumlah bar:", len(d), "dari", d.index[0].date(), "s.d.", d.index[-1].date())
v = d["Volume"]
print("Volume NaN:", int(v.isna().sum()), " nol:", int((v == 0).sum()))
print(v.describe())
print("\nVolume nol / NaN per bulan:")
m = pd.DataFrame({"nol": (v == 0) | v.isna(), "n": 1}).groupby(d.index.to_period("M")).sum()
print(m.to_string())
print("\nMedian volume per bulan (juta lembar):")
print((v.groupby(d.index.to_period("M")).median() / 1e6).round(0).to_string())
r = v / v.shift(1)
print("\nRasio volume hari ini/kemarin: kuantil", r.quantile([.01, .05, .5, .95, .99]).round(2).to_dict())
print("Hari dengan rasio > 5 atau < 0,2:")
print(d.loc[(r > 5) | (r < 0.2), ["Close", "Volume"]].to_string())
print("\n30 bar terakhir:")
print(d[["Open", "High", "Low", "Close", "Volume"]].tail(30).to_string())
print("\n10 bar April 2024:")
print(d.loc["2024-04-01":"2024-04-15", ["Close", "Volume"]].to_string())
