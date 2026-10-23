"""Детерминированные денежные потоки; AI не имеет права менять формулы."""
from collections import defaultdict


def cash_guard(bid, purchase, delivery, other, starting_cash, customer_advance,
               purchase_day, customer_payment_day, annual_interest_pct=20):
    nums=[bid,purchase,delivery,other,starting_cash,customer_advance,annual_interest_pct]
    if any(float(x)<0 for x in nums): raise ValueError('Суммы не могут быть отрицательными')
    if float(customer_advance)>float(bid): raise ValueError('Аванс не может превышать цену контракта')
    purchase_day=int(purchase_day); customer_payment_day=int(customer_payment_day)
    if purchase_day<0 or customer_payment_day<0 or customer_payment_day>730 or purchase_day>730:
        raise ValueError('Сроки должны быть от 0 до 730 дней')
    movements=defaultdict(float)
    movements[0] += float(starting_cash)+float(customer_advance)-float(delivery)-float(other)
    movements[purchase_day] -= float(purchase)
    movements[customer_payment_day] += float(bid)-float(customer_advance)
    dates=sorted(set(movements)|{0,customer_payment_day,purchase_day})
    balance=0; min_balance=0; interest=0; first_gap_day=None
    timeline=[]
    for i,day in enumerate(dates):
        balance+=movements[day]
        min_balance=min(min_balance,balance)
        if balance<0 and first_gap_day is None:first_gap_day=day
        timeline.append({'day':day,'cash_without_credit_kzt':round(balance,2)})
        if i+1<len(dates):
            interest += max(0,-balance)*(float(annual_interest_pct)/100)*(dates[i+1]-day)/365
    return {
        'funding_gap_kzt':round(max(0,-min_balance),2),
        'estimated_interest_kzt':round(interest,2),
        'gross_margin_kzt':round(float(bid)-float(purchase)-float(delivery)-float(other),2),
        'profit_before_tax_kzt':round(float(bid)-float(purchase)-float(delivery)-float(other)-interest,2),
        'first_gap_day':first_gap_day,
        'timeline':timeline,
        'notes':'Грубая модель: без налогов, валютных рисков, гарантий, штрафов и траншей; ставка условная. Не является кредитным предложением.'
    }
