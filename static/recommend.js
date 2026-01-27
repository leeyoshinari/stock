const pageSize = 20;
let page = 1;
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const defaultHeaders = {'referered': localStorage.getItem("pwd")};
  const headers = {...defaultHeaders,...(options.headers || {})};
  return originalFetch(url, {...options,headers});
};
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

function getStockRegion(code) {
    if (code.startsWith("60") || code.startsWith("68")) {
        return "sh"
    } else {
        return "sz"
    }
}

function getStockList() {
    let url = prefix + `/getRecommend?page=${page}`;
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = ""
            data.data.forEach(item => {
                let region = getStockRegion(item.code);
                s += `<div id="${item.code}" class="item-list" style="height:70px;"><div><a style="cursor:pointer;" onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a style="cursor:pointer;" onclick="show_reason('${item.code}');">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div><div><a style="cursor:pointer;" onclick="get_stock_real_figure('${item.code}');">${item.price}</a><img id="ai-${item.code}" src="${prefix}/static/ai.svg" alt="" onclick="query_stock_ai('${item.code}', '${item.name}');" /></div><div class="three-price"><span>${item.create_time}</span><span><a target="_blank" href="https://quote.eastmoney.com/concept/${region}${item.code}.html#chart-k-cyq">筹码分布</a></span></div><div class="three-price"><span style="color:${item.last_one_price>0 ? "red" : item.last_one_price<0 ? "green" : "black"};">收:${item.last_one_price}%</span><span style="color:${item.last_one_high>0 ? "red" : item.last_one_high<0 ? "green" : "black"};">高:${item.last_one_high}%</span><span style="color:${item.last_one_low>0 ? "red" : item.last_one_low<0 ? "green" : "black"};">低:${item.last_one_low}%</span></div>
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

function get_stock_figure(code) {
    fetch(prefix + `/get?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.8) + 'px';
                figure.style.height = '';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, title, data.data.x, data.data.price, data.data.volumn, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund, data.data.boll_up, data.data.boll_low);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function get_stock_real_figure(code) {
    fetch(prefix + `/query/recommend/real?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.height = '500px';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_minute_line(stockChart, title, data.data.x, data.data.price, data.data.volume);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function query_stock_ai(code, name) {
    show_modal_cover();
    fetch(prefix + `/sell/stock?price=&t=&code=${code}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

function show_reason(code) {
    fetch(prefix + `/stock/info?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data[0].name} - ${code} - ${data.data[0].region} - ${data.data[0].industry}`;
                let info = `\n\n 概念: ${data.data[0].concept}`;
                let codeEle = document.getElementById(code + '-reason');
                document.getElementById("data-tips").innerText = title + '\n\n' + codeEle.innerText + info;
                document.getElementsByClassName("stock-data")[0].style.display = "flex";
            }
        })
}

document.getElementById("stock-return").addEventListener('click', () => {
    fetch(prefix + '/query/stock/return')
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

function show_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'flex';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'flex';}
function close_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'none';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'none';}

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
