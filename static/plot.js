function plot_k_line(myChart, title, x, price, volume, ma3, ma5, ma10, ma20, qrr) {
  const downColor = '#00da3c';
  const upColor = '#ec0000';
  let option;
  myChart.clear();
  myChart.setOption(
    (option = {
      animation: false,
      title: {
        text: title,
        left: 'center',
        top: 0,
        textStyle: {
          fontSize: 13,
          fontWeight: 'bold'
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {type: 'cross'},
        borderWidth: 1,
        borderColor: '#ccc',
        padding: 10,
        textStyle: {color: '#000'}
      },
      axisPointer: {
        link: [
          {
            xAxisIndex: 'all'
          }
        ],
        label: {
          backgroundColor: '#777'
        }
      },
      visualMap: {
        show: false,
        seriesIndex: [5, 6],
        dimension: 2,
        pieces: [
          {
            value: 1,
            color: downColor
          },
          {
            value: -1,
            color: upColor
          }
        ]
      },
      grid: [
        {
          left: '10px',
          right: '30px',
          top: '20px',
          height: '300px'
        },{
          left: '30px',
          right: '30px',
          top: '350px',
          height: '80px'
        },{
          left: '30px',
          right: '30px',
          top: '440px',
          height: '40px'
        }
      ],
      xAxis: [{
          type: 'category',
          data: x,
          boundaryGap: false,
          axisLine: { onZero: false },
          splitLine: { show: false },
          min: 'dataMin',
          max: 'dataMax',
          axisPointer: {
            z: 100
          }
        },{
          type: 'category',
          gridIndex: 1,
          data: x,
          boundaryGap: false,
          axisLine: { onZero: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          min: 'dataMin',
          max: 'dataMax'
        },{
          type: 'category',
          gridIndex: 2,
          data: x,
          boundaryGap: false,
          axisLine: { onZero: false },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          min: 'dataMin',
          max: 'dataMax'
        }
      ],
      yAxis: [{
          scale: true,
          splitArea: {
            show: true
          }
        },{
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLabel: { show: false },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { show: false }
        },{
          scale: true,
          gridIndex: 2,
          splitNumber: 2,
          axisLabel: { show: false },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { show: false }
        }
      ],
      dataZoom: [{
          type: 'inside',
          xAxisIndex: [0, 1, 2],
          start: 0,
          end: 100
        },
        {
          show: false,
          xAxisIndex: [0, 1, 2],
          type: 'slider',
          start: 0,
          end: 100
        }
      ],
      series: [
        {
          name: 'Price index',
          type: 'candlestick',
          data: price,
          itemStyle: {
            color: upColor,
            color0: downColor,
            borderColor: undefined,
            borderColor0: undefined
          }
        },{
          name: 'MA3',
          type: 'line',
          data: ma3,
          smooth: true,
          showSymbol: false,
          lineStyle: {
            opacity: 0.5
          }
        },{
          name: 'MA5',
          type: 'line',
          data: ma5,
          smooth: true,
          showSymbol: false,
          lineStyle: {
            opacity: 0.5
          }
        },{
          name: 'MA10',
          type: 'line',
          data: ma10,
          smooth: true,
          showSymbol: false,
          lineStyle: {
            opacity: 0.5
          }
        },{
          name: 'MA20',
          type: 'line',
          data: ma20,
          smooth: true,
          showSymbol: false,
          lineStyle: {
            opacity: 0.5
          }
        },{
          name: 'Volume',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volume
        },{
          name: 'Qrr',
          type: 'bar',
          xAxisIndex: 2,
          yAxisIndex: 2,
          data: qrr
        }
      ]
    }),
    true
  );
  option && myChart.setOption(option);
};

function plot_trend(myChart, title, x, y1, y3, y5) {
  option = {
    title: {
      text: title,
      left: 'center',
      top: 10,
      textStyle: {
        fontSize: 13,
        fontWeight: 'bold'
      }
    },
    grid: [
      {
        left: '5%',
        right: '5%',
        top: 80,
        height: 350
      }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      }
    },
    color: ['red', 'blue', 'orange'],
    legend: [
      {
        data: ['实时', '最近3天', '最近5天'],
        x: 'center',
        y: 40,
        icon: 'line'
      }
    ],
    dataZoom: [{
        type: 'inside',
        xAxisIndex: [0],
        start: 0,
        end: 100
      },
      {
        show: false,
        xAxisIndex: [0],
        type: 'slider',
        start: 0,
        end: 100
      }
    ],
    xAxis: [
      {
        gridIndex: 0,
        type: 'category',
        boundaryGap: false,
        data: x,
        axisTick: {
          alignWithLabel: true,
          interval: 'auto'
        },
        axisLabel: {
          interval: 'auto',
          showMaxLabel: true
        }
      }
    ],
    yAxis: [
      {
        gridIndex: 0,
        name: '成交量',
        type: 'value',
        max: findMax(y1.concat(y3).concat(y5))
      },
      {gridIndex: 0}
    ],
    series: [
      {
        name: '实时',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        lineStyle: {width: 1, color: 'red'},
        data: y1
      },
      {
        name: '最近3天',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        lineStyle: {width: 1, color: 'blue'},
        data: y3
      },
      {
        name: '最近5天',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        lineStyle: {width: 1, color: 'orange'},
        data: y5
      }
    ]
};

  myChart.clear();
  myChart.setOption(option);
}

function findMax(arr) {
  let len = arr.length;
  let max = arr[0];
  while (len--) {
      if (arr[len] > max) {
          max = arr[len];
      }
  }
  return max;
}
