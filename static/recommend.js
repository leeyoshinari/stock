const pageSize = 20;
let page = 1;

document.getElementById("pre-page").addEventListener("click", () => {
    page -= 1;
    if (page <= 1) {
        document.getElementById("pre-page").disabled = 'true';
        document.getElementById("next-page").disabled = '';
    }
    getStockList();
})

document.getElementById("next-page").addEventListener("click", () => {
    page += 1;
    if (page > 1) {
        document.getElementById("pre-page").disabled = '';
    }
    getStockList();
})

function getStockList() {
    let url = prefix + `/getRecommend?page=${page}`;
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = ""
            data.data.forEach(item => {
                s += `<div id="${item.code}" class="item-list" style="height:90px;"><div><a style="cursor:pointer;" onclick="get_stock_figure('${item.code}', '${item.name}');">${item.name}</a></div><div><a style="cursor:pointer;" onclick="show_reason('${item.code}');">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div><div>${item.price}</div><div>${item.create_time}</div><div class="three-price"><span style="color:${item.last_one_price>0 ? "red" : item.last_one_price<0 ? "green" : "black"};">收:${item.last_one_price}%</span><span style="color:${item.last_one_high>0 ? "red" : item.last_one_high<0 ? "green" : "black"};">高:${item.last_one_high}%</span><span style="color:${item.last_one_low>0 ? "red" : item.last_one_low<0 ? "green" : "black"};">低:${item.last_one_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_two_price>0 ? "red" : item.last_two_price<0 ? "green" : "black"};">收:${item.last_two_price}%</span><span style="color:${item.last_two_high>0 ? "red" : item.last_two_high<0 ? "green" : "black"};">高:${item.last_two_high}%</span><span style="color:${item.last_two_low>0 ? "red" : item.last_two_low<0 ? "green" : "black"};">低:${item.last_two_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_three_price>0 ? "red" : item.last_three_price<0 ? "green" : "black"};">收:${item.last_three_price}%</span><span style="color:${item.last_three_high>0 ? "red" : item.last_three_high<0 ? "green" : "black"};">高:${item.last_three_high}%</span><span style="color:${item.last_three_low>0 ? "red" : item.last_three_low<0 ? "green" : "black"};">低:${item.last_three_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_four_price>0 ? "red" : item.last_four_price<0 ? "green" : "black"};">收:${item.last_four_price}%</span><span style="color:${item.last_four_high>0 ? "red" : item.last_four_high<0 ? "green" : "black"};">高:${item.last_four_high}%</span><span style="color:${item.last_four_low>0 ? "red" : item.last_four_low<0 ? "green" : "black"};">低:${item.last_four_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_five_price>0 ? "red" : item.last_five_price<0 ? "green" : "black"};">收:${item.last_five_price}%</span><span style="color:${item.last_five_high>0 ? "red" : item.last_five_high<0 ? "green" : "black"};">高:${item.last_five_high}%</span><span style="color:${item.last_five_low>0 ? "red" : item.last_five_low<0 ? "green" : "black"};">低:${item.last_five_low}%</span></div><div id="${item.code}-reason" style="display:none;">${item.content}</div></div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
            document.querySelectorAll('[id*="copy-"]').forEach( item => {
                item.addEventListener('click', (event) => {
                    if (navigator.clipboard && window.isSecureContext) {
                        navigator.clipboard.writeText(event.target.id.split('-')[1]);
                    }
                })
            })
        })
}

function get_stock_figure(code, name) {
    fetch(prefix + `/get?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let figure = document.getElementById("figure");
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, `${name} - ${code}`, data.data.x, data.data.price, data.data.volumn, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function show_reason(code) {
    let codeEle = document.getElementById(code + '-reason');
    document.getElementById("data-tips").innerText = code + '\n' + codeEle.innerText;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

document.getElementById("stock-return").addEventListener('click', () => {
    let url = prefix + '/query/stock/return';
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = `<div class="header">每只股票买入5000元的收益</div><div><div class="return-table" style="font-weight:bold;"><span>时间</span><span>第一天</span><span>第二天</span><span>第三天</span><span>第四天</span><span>第五天</span></div>
                    <div class="return-table"><span>收盘时</span><span>${data.data.r1}</span><span>${data.data.r2}</span><span>${data.data.r3}</span><span>${data.data.r4}</span><span>${data.data.r5}</span></div>
                    <div class="return-table"><span>最高时</span><span>${data.data.r1h}</span><span>${data.data.r2h}</span><span>${data.data.r3h}</span><span>${data.data.r4h}</span><span>${data.data.r5h}</span></div>
                    <div class="return-table"><span>最低时</span><span>${data.data.r1l}</span><span>${data.data.r2l}</span><span>${data.data.r3l}</span><span>${data.data.r4l}</span><span>${data.data.r5l}</span></div></div>`
            document.getElementById("data-tips").innerHTML = s;
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
})

document.getElementById("stock-return-line").addEventListener('click', () => {
    fetch(prefix + '/query/stock/return')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let figure = document.getElementById("figure");
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_trend(stockChart, data.data.x, data.data.y1, data.data.y1h, data.data.y1l, data.data.y2, data.data.y2h, data.data.y2l,
                    data.data.y3, data.data.y3h, data.data.y3l, data.data.y4, data.data.y4h, data.data.y4l, data.data.y5, data.data.y5h, data.data.y5l
                );
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
})
const overlay_data = document.querySelector('.stock-data');
const overlay_chart = document.querySelector('.stock-chart');
document.getElementById("pre-page").disabled = 'true';
overlay_data.addEventListener('click', function(event) {
  if (event.target === overlay_data) {overlay_data.style.display = 'none';}
});
overlay_chart.addEventListener('click', function(event) {
  if (event.target === overlay_chart) {overlay_chart.style.display = 'none';}
});
getStockList();
