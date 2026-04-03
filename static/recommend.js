const pageSize = 20;
const showFlag = window.location.href.endsWith("trump");
const currDate = new Date();
const currentDay = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(currDate);
const searchType = document.location.search.split('=')[1];
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
    let url = `${prefix}/getRecommend?page=${page}&source=${localStorage.getItem('source')}`;
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = "";
            let he = "";
            data.data.forEach(item => {
                let region = getStockRegion(item.code);
                let deleteR = '';
                if (showFlag) {
                    deleteR = `<div><a onclick="delete_data('${item.id}')">删除</a></div>`;
                }
                if (searchType === "5") {
                    he = "<div>名称</div><div>代码</div><div>选出价</div><div>选出日期</div><div>第一天</div><div>第二天</div><div>第三天</div><div>第四天</div><div>第五天</div><div>卖出时间</div>";
                    s += `<div id="${item.id}" class="item-list" style="height:70px;"><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="show_reason('${item.code}','${item.id}',0);">${item.code}</a><!--img id="copy-${item.id}" src="${prefix}/static/copy.svg" alt="" /--></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.price}</a><img id="ai-${item.id}" src="${prefix}/static/sell.svg" alt="" onclick="query_stock_ai('${item.code}', '${item.name}');" style="width:18px;" /></div><div class="three-price"><span>${item.create_time}</span><span><a target="_blank" href="https://quote.eastmoney.com/concept/${region}${item.code}.html#chart-k-cyq">筹码分布</a></span></div>
                      <div class="three-price"><span style="color:${item.last_one_price>0 ? "red" : item.last_one_price<0 ? "green" : "black"};">收:${item.last_one_price}%</span><span style="color:${item.last_one_high>0 ? "red" : item.last_one_high<0 ? "green" : "black"};">高:${item.last_one_high}%</span><span style="color:${item.last_one_low>0 ? "red" : item.last_one_low<0 ? "green" : "black"};">低:${item.last_one_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_two_price>0 ? "red" : item.last_two_price<0 ? "green" : "black"};">收:${item.last_two_price}%</span><span style="color:${item.last_two_high>0 ? "red" : item.last_two_high<0 ? "green" : "black"};">高:${item.last_two_high}%</span><span style="color:${item.last_two_low>0 ? "red" : item.last_two_low<0 ? "green" : "black"};">低:${item.last_two_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_three_price>0 ? "red" : item.last_three_price<0 ? "green" : "black"};">收:${item.last_three_price}%</span><span style="color:${item.last_three_high>0 ? "red" : item.last_three_high<0 ? "green" : "black"};">高:${item.last_three_high}%</span><span style="color:${item.last_three_low>0 ? "red" : item.last_three_low<0 ? "green" : "black"};">低:${item.last_three_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_four_price>0 ? "red" : item.last_four_price<0 ? "green" : "black"};">收:${item.last_four_price}%</span><span style="color:${item.last_four_high>0 ? "red" : item.last_four_high<0 ? "green" : "black"};">高:${item.last_four_high}%</span><span style="color:${item.last_four_low>0 ? "red" : item.last_four_low<0 ? "green" : "black"};">低:${item.last_four_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_five_price>0 ? "red" : item.last_five_price<0 ? "green" : "black"};">收:${item.last_five_price}%</span><span style="color:${item.last_five_high>0 ? "red" : item.last_five_high<0 ? "green" : "black"};">高:${item.last_five_high}%</span><span style="color:${item.last_five_low>0 ? "red" : item.last_five_low<0 ? "green" : "black"};">低:${item.last_five_low}%</span></div>
                      <div class="three-price" style="color:${item.sale_time === currentDay ? "red" : ""};"><a onclick="show_reason('${item.code}','${item.id}',1);"><span>${item.sale_time}</span><span>${item.sale_price}</span></a></div><div id="${item.id}-reason" style="display:none;">${item.content}</div></div>`;
                } else {
                    he = "<div>名称</div><div>代码</div><div>选出价</div><div>选出日期</div><div>卖出价</div><div>卖出时间</div>";
                    s += `<div id="${item.id}" class="item-list" style="height:42px;"><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="show_reason('${item.code}','${item.id}',0);">${item.code}</a><!--img id="copy-${item.id}" src="${prefix}/static/copy.svg" alt="" /--></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.price}</a><img id="ai-${item.id}" src="${prefix}/static/sell.svg" alt="" onclick="query_stock_ai('${item.code}', '${item.name}');" style="width:18px;" /></div><div><a target="_blank" href="https://quote.eastmoney.com/concept/${region}${item.code}.html#chart-k-cyq">${item.create_time}</a></div>
                        <div style="color:${item.sale_time === currentDay ? "red" : ""};"><a onclick="show_reason('${item.code}','${item.id}',1);">${item.sale_price}</a></div><div style="color:${item.sale_time === currentDay ? "red" : ""};">${item.sale_time}</div>${deleteR}<div id="${item.id}-reason" style="display:none;">${item.content}</div></div>`;
                }
            })
            document.getElementsByClassName("item-header")[0].innerHTML = he;
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
            // document.querySelectorAll('[id*="copy-"]').forEach( item => {
            //     item.addEventListener('click', (event) => {
            //         if (navigator.clipboard && window.isSecureContext) {
            //             navigator.clipboard.writeText(event.target.id.split('-')[1]);
            //         }
            //     })
            // })
        })
}

function get_stock_figure(code) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/get?code=${code}&site=${site}`)
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
                plot_k_line(stockChart, title, data.data.x, data.data.price, data.data.volume, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund, data.data.boll_up, data.data.boll_low, data.data.coord);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function get_stock_real_figure(code) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/query/day/k?code=${code}&site=${site}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.8) + 'px';
                figure.style.height = '500px';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_minute_line(stockChart, title, data.data.x, data.data.price, data.data.price_avg, data.data.volume);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function query_stock_ai(code, name) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/ai/sell?site=${site}&code=${code}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
            document.getElementById("data-tips").style.width = '70%';
            document.getElementById("data-tips").style.transform = 'translate(0%,0%)';
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

function delete_data(codeId) {
    fetch(`${prefix}/deleteRecommend?rId=${codeId}`)
        .then(res => res.json())
        .then(data => {getStockList();})
}

function show_reason(code, rId, index) {
    fetch(`${prefix}/stock/info?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data[0].name} - ${code} - ${data.data[0].region} - ${data.data[0].industry}`;
                let info = `\n\n 概念: ${data.data[0].concept}`;
                let codeEle = document.getElementById(rId + '-reason');
                document.getElementById("data-tips").innerText = title + '\n\n' + codeEle.innerText.split('LEE')[index] + info;
                document.getElementsByClassName("stock-data")[0].style.display = "flex";
            }
        })
}

document.getElementById("stock-return").addEventListener('click', () => {
    let fee = document.location.href.indexOf('fee');
    fetch(`${prefix}/query/stock/return?fee=${fee}`)
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

document.getElementById('stock-in-hand').addEventListener('click', () => {
    let source = localStorage.getItem('source');
    document.getElementById('stock-in-hand').innerText = source==='1' ? "持仓列表" : "推荐列表";
    localStorage.setItem('source', source==='1' ? 0 : 1);
    getStockList();
})

localStorage.setItem('source', 0);
getStockList();
