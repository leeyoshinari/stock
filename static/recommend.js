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
                s += `<div id="${item.code}" class="item-list" style="height:90px;"><div>${item.name}</div><div>${item.code}</div><div>${item.price}</div><div>${item.create_time}</div><div class="three-price"><span style="color:${item.last_one_price>0 ? "red" : item.last_one_price<0 ? "green" : "black"};">收:${item.last_one_price}%</span><span style="color:${item.last_one_high>0 ? "red" : item.last_one_high<0 ? "green" : "black"};">高:${item.last_one_high}%</span><span style="color:${item.last_one_low>0 ? "red" : item.last_one_low<0 ? "green" : "black"};">低:${item.last_one_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_two_price>0 ? "red" : item.last_two_price<0 ? "green" : "black"};">收:${item.last_two_price}%</span><span style="color:${item.last_two_high>0 ? "red" : item.last_two_high<0 ? "green" : "black"};">高:${item.last_two_high}%</span><span style="color:${item.last_two_low>0 ? "red" : item.last_two_low<0 ? "green" : "black"};">低:${item.last_two_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_three_price>0 ? "red" : item.last_three_price<0 ? "green" : "black"};">收:${item.last_three_price}%</span><span style="color:${item.last_three_high>0 ? "red" : item.last_three_high<0 ? "green" : "black"};">高:${item.last_three_high}%</span><span style="color:${item.last_three_low>0 ? "red" : item.last_three_low<0 ? "green" : "black"};">低:${item.last_three_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_four_price>0 ? "red" : item.last_four_price<0 ? "green" : "black"};">收:${item.last_four_price}%</span><span style="color:${item.last_four_high>0 ? "red" : item.last_four_high<0 ? "green" : "black"};">高:${item.last_four_high}%</span><span style="color:${item.last_four_low>0 ? "red" : item.last_four_low<0 ? "green" : "black"};">低:${item.last_four_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_five_price>0 ? "red" : item.last_five_price<0 ? "green" : "black"};">收:${item.last_five_price}%</span><span style="color:${item.last_five_high>0 ? "red" : item.last_five_high<0 ? "green" : "black"};">高:${item.last_five_high}%</span><span style="color:${item.last_five_low>0 ? "red" : item.last_five_low<0 ? "green" : "black"};">低:${item.last_five_low}%</span></div></div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
        })
}

document.getElementById("stock-return").addEventListener('click', () => {
    let url = prefix + '/query/stock/return';
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = `<div class="header">每只股票买入一万元的收益</div><div><div class="return-table"><span>日期</span><span>第一天</span><span>第二天</span><span>第三天</span><span>第四天</span><span>第五天</span></div>
                    <div class="return-table"><span>收盘时</span><span>${data.data.r1}</span><span>${data.data.r2}</span><span>${data.data.r3}</span><span>${data.data.r4}</span><span>${data.data.r5}</span></div>
                    <div class="return-table"><span>最高时</span><span>${data.data.r1h}</span><span>${data.data.r2h}</span><span>${data.data.r3h}</span><span>${data.data.r4h}</span><span>${data.data.r5h}</span></div>
                    <div class="return-table"><span>最低时</span><span>${data.data.r1l}</span><span>${data.data.r2l}</span><span>${data.data.r3l}</span><span>${data.data.r4l}</span><span>${data.data.r5l}</span></div></div>`
            document.getElementById("data-tips").innerHTML = s;
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
})
const overlay_data = document.querySelector('.stock-data');
document.getElementById("pre-page").disabled = 'true';
overlay_data.addEventListener('click', function(event) {
  if (event.target === overlay_data) {overlay_data.style.display = 'none';}
});
getStockList();
