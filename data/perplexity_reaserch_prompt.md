Find a lot of news from different point of view. That relates closely to topic given in last paragraph. Explore diverse information portals and other written media. Keep it balanced from left-leaning to center, to right-leaning political views.
I want to give you news text and you return json in structure like this:
News should be closely related to Poland and polish events, politics, culture.

This JSON must be fillled with newes links that relates for this topic.
Must be at least 10 links from news with variouis political inclinations
vatios views of words, various political agenda.

VERY IMPORTANT RULES
Don't change JSON strucutre. DO NOT modify fields, do not add new fileds

Available political_inclination are (Use ONLY them):
- left
- center-left
- center
- center-right
- right

{
"topic_id": "trump_gaza_peace_council",
"language": "pl",
"news_text": "Samorządy w całej Polsce podnoszą ceny za wywóz śmieci — w niektórych już 53 zł od osoby, nawet 185 zł miesięcznie za gospodarstwo; powody to droższa energia, paliwo i wyższa płaca minimalna oraz kary za niespełnienie celów recyklingu, które przerzucają koszty na mieszkańców, podczas gdy producenci opakowań nie płacą, a w Bielsku-Białej i Rybniku opłaty wzrosły o 25% do 35–38 zł, zaś w Warszawie podwyżki planowane są na kwiecień 2026.",
"sources": [
{
"name": "Gazeta Prawna",
"url": "https://www.gazetaprawna.pl/wiadomosci/kraj/artykuly/10621086,podwyzki-oplat-za-wywoz-smieci-ceny-stawki-2026.html",
"political_inclination": "left"
},
{
"name": "Money PL",
"url": "https://www.money.pl/gospodarka/polskie-miasta-drastycznie-podnosza-oplaty-za-smieci-fala-podwyzek-7241243024181760a.html",
"political_inclination": "right"
},
{
"name": "Forsal",
"url": "https://forsal.pl/nieruchomosci/artykuly/10581809,53-zlote-za-osobe-za-wywoz-smieci-segregowanych-i-159-zlotych-za-osobe-w-przypadku-odpadow-niesegregowanych-takie-podwyzki-czekaja-od-1-stycznia-2026-r.html",
"political_inclination": "right-center"
}
]
}





YOUR NEWS AS INPUT IS: