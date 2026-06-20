# Snet.Iot.Daq 架构设计文档

> **版本**: v1.0 | **更新日期**: 2026-06-21 | **框架**: .NET 10.0 | **类型**: WPF 桌面应用

---

## 目录

1. [项目概述](#1-项目概述)
2. [解决方案结构](#2-解决方案结构)
3. [核心 UML 类图](#3-核心-uml-类图)
4. [核心流程图](#4-核心流程图)
5. [设计模式分析](#5-设计模式分析)
6. [代码详解与使用方式](#6-代码详解与使用方式)

---

## 1. 项目概述

**Snet.Iot.Daq** 是一个基于 .NET 10 的开源工业物联网（IIoT）数据采集工具，采用插件化架构，支持运行时热插拔。核心能力：

- **数据采集 (DAQ)**: 通过 IDaq 插件接口，支持 Siemens、Modbus、Mitsubishi、Omron、AllenBradley、OPC DA/UA 等 30+ 种工业协议
- **消息传输 (MQ)**: 通过 IMq 插件接口，支持 MQTT、RabbitMQ、Kafka 等消息队列
- **内置服务**: 内嵌 MQTT Broker 和 OPC UA Server
- **插件热插拔**: 基于 `AssemblyLoadContext`，运行时加载/卸载插件，无需重启
- **点位管理**: 基于 SQLite 的地址配置与持久化

---

## 2. 解决方案结构

```mermaid
flowchart LR
    A["Snet.Iot.Daq\n(WPF 主程序)\nnet10.0-windows"] --> B["Snet.Iot.Daq.Core\n(核心类库)\nnet10.0"]
    
    B --> C["Snet.Core\n(基础库)"]
    B --> D["Snet.Model\n(接口定义库)"]
    B --> E["MQTTnet\n(MQTT通信)"]
    B --> F["OPC Foundation\n(OPC UA)"]
    B --> G["sqlite-net-pcl\n(SQLite ORM)"]
    B --> H["CommunityToolkit.Mvvm\n(MVVM框架)"]
    
    A --> I["Snet.Windows.Controls\n(WPF控件库)"]
    
    J["Snet.Iot.Daq.AddressTest\n(地址测试工具)"] --> B
    K["Snet.Iot.Daq.MqPerformanceTesting\n(MQ性能测试)"] --> B
    L["Snet.Pack.Manage.Tool\n(插件打包工具)"] --> B

    classDef main fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1
    classDef core fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    classDef ext fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c
    classDef aux fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,color:#4a148c
    class A,I main
    class B core
    class C,D,E,F,G,H ext
    class J,K,L aux
```

| 项目 | 类型 | 框架 | 说明 |
|------|------|------|------|
| **Snet.Iot.Daq** | WPF 应用 | net10.0-windows | 主程序，提供 UI 界面与用户交互 |
| **Snet.Iot.Daq.Core** | 类库 | net10.0 | 核心逻辑层，包含 Handler、插件管理、数据模型、服务端实现 |
| **Snet.Iot.Daq.AddressTest** | 控制台 | - | 地址读写功能测试工具 |
| **Snet.Iot.Daq.MqPerformanceTesting** | 控制台 | - | MQTT 消息传输性能压测工具 |
| **Snet.Pack.Manage.Tool** | 控制台 | - | 插件 ZIP 打包管理工具 |

---

## 3. 核心 UML 类图

### 3.1 整体架构类图

```mermaid
classDiagram
    direction LR

    class App {
        +LanguageOperate$
        +EditModels
        -Init()
    }

    class GlobalConfigModel {
        +AddressDict
        +PluginDict
        +sqliteOperate
        +mqttService
        +uaService
        +DbLock
    }

    class IAddressModel {
        <<interface>>
        +Address
        +Type
        +Convert()
        +UpdateAsync()
    }

    class AddressModelCore {
        <<abstract>>
        +Index
        +Guid
        +AnotherName
        +Convert()
    }

    class AddressModel {
        +ExpandParam
        +UpdateAsync()
    }

    class PluginConfigModel {
        +Guid
        +SN
        +Type
        +Name
        +Status
        +UpdateLocalConfig()
    }

    class DqaHandler {
        -icoDaq
        +ReadAsync()
        +WriteAsync()
        +SubscribeAsync()
    }

    class MqHandler {
        -icoMq
        +ProduceAsync()
        +ConsumerAsync()
    }

    class PluginHandlerCore {
        +PluginOperate$
        +InitPlugin()
        +TestReadAsync()
    }

    class IDaq {
        <<interface>>
        +OnAsync()
        +ReadAsync()
        +OnDataEventAsync
    }

    class IMq {
        <<interface>>
        +OnAsync()
        +ProduceAsync()
        +OnDataEventAsync
    }

    class MqttServiceOperate {
        内置 MQTT Broker
    }

    class OpcUaServiceOperate {
        内置 OPC UA Server
    }

    App ..> GlobalConfigModel : 初始化
    App ..> PluginHandlerCore : 插件加载
    GlobalConfigModel o-- AddressModel : 管理
    GlobalConfigModel o-- PluginConfigModel : 管理
    GlobalConfigModel o-- MqttServiceOperate : 持有
    GlobalConfigModel o-- OpcUaServiceOperate : 持有
    IAddressModel <|.. AddressModelCore : 实现
    AddressModelCore <|-- AddressModel : 继承
    PluginConfigModel ..> DqaHandler : 创建
    PluginConfigModel ..> MqHandler : 创建
    DqaHandler ..> IDaq : 管理
    MqHandler ..> IMq : 管理
    PluginHandlerCore ..> PluginConfigModel : 创建实例
```

### 3.2 数据模型继承链

```mermaid
classDiagram
    direction TB

    class BindNotify {
        <<抽象>> (Snet.Core)
        +GetProperty~T~() T
        +SetProperty~T~(value)
        +OnPropertyChanged()
        动态属性存储 + INotifyPropertyChanged
    }

    class DaqPluginOperateModel {
        <<抽象>> (Snet.Model)
        +Address string
        +Type DataType
        +Length ushort
        +EncodingType EncodingType
    }

    class ReadModel {
        <<抽象>> (Snet.Model)
        +ReadAsync()
        +WriteAsync()
    }

    class AddressModelCore {
        <<抽象>>
        +Index int [PK, AutoIncrement]
        +Guid string
        +AnotherName string [Unique]
        +Describe string
        +Topic string
        +SimplifyValue bool
        +Convert() AddressDetails
    }

    class AddressModel {
        +ExpandParam string
        +UpdateAsync() Task
        +Revoke(int index)
    }

    class PluginConfigModel {
        +Guid string
        +SN string
        +Type PluginType
        +Name string
        +Param string
        +Status bool
        +WAModel WebApi
        +UpdateLocalConfig() bool
    }

    BindNotify <|-- DaqPluginOperateModel
    DaqPluginOperateModel <|-- ReadModel
    ReadModel <|-- AddressModelCore
    AddressModelCore <|-- AddressModel
    BindNotify <|-- PluginConfigModel

    class IAddressModel {
        <<interface>>
    }
    IAddressModel <|.. AddressModelCore
```

### 3.3 Handler 继承链

```mermaid
classDiagram
    direction LR

    class CoreUnify~T,TBasics~ {
        <<abstract>> (Snet.Core)
        +T Instance(TBasics basics)$
        +OnDataEventHandlerAsync(guid, e) Task
        +OnInfoEventHandlerAsync(guid, e) Task
        +Dispose()
        +DisposeAsync()
        线程安全单例工厂
    }

    class DqaHandler {
        -ConcurrentDictionary~string,IDaq~ icoDaq
        -ConcurrentDictionary~string,EventHandlerAsync~ _dataHandlers
        +ReadAsync(guid, address) Task
        +WriteAsync(guid, address, write) Task
        +SubscribeAsync(guid, address) Task
        +WAOnAsync(guid, model) Task
    }

    class MqHandler {
        -ConcurrentDictionary~string,IMq~ icoMq
        -ConcurrentDictionary~string,EventHandlerAsync~ _dataHandlers
        +ProduceAsync(guid, address, value) Task
        +ConsumerAsync(guid, topic) Task
    }

    CoreUnify~DqaHandler,PluginConfigModel~ <|-- DqaHandler
    CoreUnify~MqHandler,PluginConfigModel~ <|-- MqHandler
```

---

## 4. 核心流程图

### 4.1 应用启动流程

```mermaid
flowchart TD
    A["App.OnStartup()"] --> B{"单实例检查\nSingleInstance"}
    B -->|"非首实例"| C["唤醒已有窗口\n→ Shutdown"]
    B -->|"首实例"| D["Init() 初始化"]
    
    subgraph init ["初始化阶段"]
        D --> E["注册依赖注入\nInjectionWpf.AddService"]
        E --> F["注册用户控件\nSelectDevice/SelectAddress/Handler"]
        F --> G["创建 SQLite 表\nAddressModel"]
        G --> H["加载插件列表\nPluginList.json"]
        H --> I["初始化插件\nPluginOperate.InitPlugin"]
        I --> J["获取已有插件\nPluginHandler.GetAllPlugin"]
        J --> K["获取已有地址\nAddressHandler.GetAllAddress"]
        J --> L["获取已有项目\nProjectHandler.GetAllProject"]
    end
    
    subgraph startup ["启动阶段"]
        K --> M["注册全局异常捕获\n3层异常处理"]
        L --> M
        M --> N["加载图标资源\nicons.xaml"]
        N --> O["创建主窗口\nMainWindow.Show()"]
        O --> P["注册主窗口句柄\nRegisterMainWindow"]
        P --> Q["应用就绪"]
    end

    classDef stage fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1
    classDef decision fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c
    classDef endpoint fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    class A,D,M,N,O,P stage
    class B decision
    class C,Q endpoint
```

### 4.2 数据采集完整流程

```mermaid
flowchart TD
    A["用户/系统触发\n读取/订阅地址"] --> B["DqaHandler.OpenAsync(guid)"]
    
    subgraph connection ["设备连接管理"]
        B --> C{"缓存中存在 IDaq?\nicoDaq.TryGetValue"}
        C -->|"否"| D["插件工厂创建实例\nbasics.CreateNewObjectAsync()"]
        D --> E["ConcurrentDictionary.GetOrAdd\n原子操作防竞态"]
        E --> F{"引用相同?\nReferenceEquals"}
        F -->|"否 (竞态)"| G["释放多余实例\nawait newOperate.DisposeAsync()"]
        F -->|"是"| H["检查连接状态\noperate.GetStatusAsync()"]
        C -->|"是"| H
    end
    
    subgraph event_reg ["事件注册"]
        H --> I{"已连接?\nresult.Status"}
        I -->|"是"| M["跳过事件注册"]
        I -->|"否"| J["移除旧事件委托\nTryRemove oldHandler"]
        J --> K["创建 per-guid 新委托\n_dataHandlers[guid]"]
        K --> L["订阅事件\n+= OnDataEventAsync\n+= OnInfoEventAsync"]
        L --> M["执行打开操作\nawait operate.OnAsync()"]
    end
    
    subgraph data_op ["数据操作"]
        M --> N["返回 (IDaq, OperateResult)"]
        N --> O{"操作类型?"}
        O -->|"Read"| P["地址转换\naddress.Convert()\n→ AddressDetails"]
        P --> Q["执行读取\noperate.ReadAsync(address)"]
        O -->|"Write"| R["封装写入字典\nConcurrentDictionary&lt;string, WriteModel&gt;"]
        R --> S["执行写入\noperate.WriteAsync(keys)"]
        O -->|"Subscribe"| T["地址转换后订阅\noperate.SubscribeAsync(address)"]
    end
    
    subgraph callback ["事件回调"]
        Q --> U["设备数据变化"]
        S --> U
        T --> U
        U --> V["触发 OnDataEventAsync\n转发到上层"]
        V --> W["UI 更新 / MQ传输"]
    end

    classDef connect fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1
    classDef event fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    classDef operate fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#bf360c
    class B,C,D,E,F,G,H,I,J,K,L,M connect
    class J,K,L,V,W event
    class N,O,P,Q,R,S,T operate
```

### 4.3 插件热插拔流程

```mermaid
flowchart TD
    A1["加载 ①：上传 ZIP → 解压 lib\n创建 ALC → 流式加载 DLL"]
    A2["加载 ②：扫描 IDaq/IMq 实现\n实例化插件 CreateAsync()"]
    A3["加载 ③：注册 IOC 容器\n开始数据采集"]

    B1["卸载 ①：停止采集 OffAsync()\n释放实例 DisposeAsync()"]
    B2["卸载 ②：注销事件委托\n移除 IOC → ALC.Unload()"]
    B3["卸载 ③：GC.Collect()\n删除插件文件"]

    A1 --> A2 --> A3
    B1 --> B2 --> B3

    style A1 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style A2 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style A3 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style B1 fill:#ffebee,stroke:#c62828,stroke-width:2px
    style B2 fill:#ffebee,stroke:#c62828,stroke-width:2px
    style B3 fill:#ffebee,stroke:#c62828,stroke-width:2px
```

**关键技术要点**

| 要点 | 说明 |
|------|------|
| 可回收上下文 | `AssemblyLoadContext(isCollectible: true)` 支持运行时卸载 |
| 流式加载 | `MemoryStream + LoadFromStream`，无文件锁，支持即时删除 |
| 类型一致性 | 共享接口从默认上下文加载，确保 `as`/`is` 转换正确 |
| 并发安全 | `ConcurrentDictionary` 管理实例与上下文引用 |
| 双插件类型 | DAQ 采集插件 + MQ 传输插件，独立生命周期 |

### 4.4 数据采集 → 消息传输数据流

```mermaid
flowchart TD
    subgraph field ["工业现场层"]
        direction LR
        PLC1["Siemens S7-1200"]
        PLC2["Modbus TCP"]
        PLC3["OPC UA Server"]
        PLC4["自定义协议"]
    end

    subgraph plugin ["插件层 ALC 隔离"]
        direction LR
        DAQ1["Snet.Siemens\nIDaq"]
        DAQ2["Snet.Modbus\nIDaq"]
        DAQ3["Snet.OpcUa\nIDaq"]
        DAQ4["Snet.Freedom\nIDaq"]
    end

    subgraph core ["核心处理层"]
        direction LR
        HANDLER["DqaHandler\n设备生命周期\n事件订阅/转发"]
        ADDRESS["AddressModel\n点位映射\nSimplifyValue"]
    end

    subgraph transport ["消息传输层"]
        direction LR
        MQH["MqHandler\n生产 / 消费"]
        MQ1["Snet.Mqtt\nIMq"]
        MQ2["Snet.RabbitMQ\nIMq"]
        MQ3["Snet.Kafka\nIMq"]
    end

    subgraph target ["目标系统"]
        direction LR
        BROKER["MQTT / RabbitMQ / Kafka"]
        APP["上位机 / SCADA / 云平台"]
    end

    PLC1 --> DAQ1
    PLC2 --> DAQ2
    PLC3 --> DAQ3
    PLC4 --> DAQ4

    DAQ1 --> HANDLER
    DAQ2 --> HANDLER
    DAQ3 --> HANDLER
    DAQ4 --> HANDLER

    HANDLER -->|OnDataEventAsync| ADDRESS
    ADDRESS -->|Topic 非空| MQH

    MQH --> MQ1
    MQH --> MQ2
    MQH --> MQ3

    MQ1 --> BROKER
    MQ2 --> BROKER
    MQ3 --> BROKER
    BROKER --> APP

    style field fill:#ffebee,stroke:#c62828,stroke-width:2px
    style plugin fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style core fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style transport fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style target fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

> **数据流说明**：PLC 设备数据经 IDaq 插件采集 → DqaHandler 统一管理生命周期与事件转发 → AddressModel 点位映射（可精简数据）→ 若配置了 Topic 则通过 MqHandler 转发至 IMq 插件 → 最终送达 MQTT/RabbitMQ/Kafka Broker → 上位机/云平台消费。

---

## 5. 设计模式分析

### 5.1 插件架构 (Plugin Architecture)

最核心的设计模式。整个系统围绕两个扩展接口构建：

| 接口 | 命名空间 | 职责 | 典型插件 |
|------|----------|------|----------|
| `IDaq` | `Snet.Model.@interface` | 数据采集：连接设备、读取/写入地址、订阅变化 | Snet.Siemens, Snet.Modbus, Snet.OpcUa |
| `IMq` | `Snet.Model.@interface` | 消息传输：生产/消费消息、连接消息中间件 | Snet.Mqtt, Snet.RabbitMQ, Snet.Kafka |

**技术实现**:
- 基于 .NET `AssemblyLoadContext(isCollectible: true)` 实现可回收程序集上下文
- 使用 `MemoryStream` + `LoadFromStream` 流式加载 DLL，避免文件锁
- 插件 ZIP 解压 → 创建上下文 → 扫描接口 → 实例化 → 注册 IOC
- 卸载时逐步释放：停止采集 → Dispose → 移除 IOC → 卸载上下文 → GC 回收 → 删除文件

**对应代码**: `Snet.Iot.Daq.Core/handler/PluginHandlerCore.cs`

```csharp
// 初始化插件
PluginHandlerCore.PluginOperate.InitPlugin(
    item.PluginDetails.Path,
    string.Format(GlobalConfigModel.InterfaceFullName, item.Type)
);

// 通过配置创建插件实例
public static async Task<T?> CreateNewObjectAsync<T>(this PluginConfigModel plugin)
    => await PluginOperate.CreateAsync<T>(plugin.Name, plugin.Param, plugin.Type);
```

### 5.2 单例模式 (Singleton) - `CoreUnify<T, TBasics>`

Handler 类通过泛型基类 `CoreUnify<T, TBasics>` 实现"按配置键的单例"——同一个插件配置（相同 PluginConfigModel）始终返回同一个 Handler 实例。

**对应代码**: `Snet.Iot.Daq.Core/handler/DqaHandler.cs`、`MqHandler.cs`

```csharp
public class DqaHandler : CoreUnify<DqaHandler, PluginConfigModel>, IDisposable, IAsyncDisposable
{
    // Instance(basics) 工厂方法保证相同配置返回同一实例
}
```

### 5.3 MVVM 模式 (Model-View-ViewModel)

使用 `CommunityToolkit.Mvvm` 和 `Snet.Windows.Controls` 框架：

| 层 | 路径 | 示例 |
|----|------|------|
| **Model** | `Snet.Iot.Daq/data/` | `AddressModel`, `GlobalConfigModel` |
| **View** | `Snet.Iot.Daq/view/` | `MainWindow.xaml`, `SelectDevice.xaml` |
| **ViewModel** | `Snet.Iot.Daq/viewModel/` | `MainWindowModel`, `HandlerModel` |

**依赖注入**:
```csharp
// App.Init() 中注册
InjectionWpf.UserControl<SelectDevice, SelectDeviceModel>(true);
InjectionWpf.UserControl<SelectAddress, SelectAddressModel>(true);
InjectionWpf.UserControl<view.Handler, HandlerModel>(true);
```

### 5.4 观察者模式 (Observer) - 事件驱动数据流

数据从设备 → Handler → UI / MQ 的流转完全基于事件：

```csharp
// DqaHandler 内部注册设备事件
EventHandlerAsync<EventDataResult> newDataHandler = 
    async (sender, e) => await Operate_OnDataEventAsync(sender, e, guid);
operate.OnDataEventAsync += newDataHandler;

// 事件触发后转发到上层
private async Task Operate_OnDataEventAsync(object? sender, EventDataResult e, string guid)
{
    await OnDataEventHandlerAsync(guid, e);  // 由 CoreUnify 基类提供
}
```

### 5.5 资源管理模式 - `IAsyncDisposable`

所有 Handler 和插件实例都实现了 `IAsyncDisposable`，使用 `try/finally` 确保资源可靠释放：

```csharp
// 测试读取 - 确保资源释放
public static async Task<OperateResult> TestReadAddressAsync(this IAddressModel model, PluginConfigModel plugin)
{
    IDaq? daqNew = await plugin.CreateNewObjectAsync<IDaq>();
    try
    {
        // ... 执行读取操作
    }
    finally
    {
        await daqNew.OffAsync();
        await daqNew.DisposeAsync();
    }
}
```

### 5.6 并发安全策略

| 组件 | 策略 | 说明 |
|------|------|------|
| `icoDaq` / `icoMq` | `ConcurrentDictionary` | 线程安全的设备实例缓存 |
| `_dataHandlers` | `ConcurrentDictionary` | per-guid 事件委托管理，防止多设备事件泄漏 |
| `AddressDict` / `PluginDict` | `ConcurrentDictionary` | 全局地址和插件缓存 |
| `DbLock` | `lock` 同步 | SQLite 不是线程安全的，所有数据库操作必须加锁 |
| 批量操作 | `Task.WhenAll` + `ConcurrentBag` | 并行发送消息，ConcurrentBag 收集错误 |

---

## 6. 代码详解与使用方式

### 6.1 项目编译与运行

```bash
# 1. 克隆仓库
git clone https://github.com/shunnet/Daq.git
cd Daq

# 2. 使用 Visual Studio 2022+ 打开
Snet.Iot.Daq.sln

# 3. 选择 Debug / Release 构建

# 4. 运行
./Snet.Iot.Daq/bin/Debug/net10.0-windows/Snet.Iot.Daq.exe
```

### 6.2 添加一个数据采集点位

```csharp
// 1. 创建地址模型
IAddressModel address = new AddressModel
{
    Address = "DB1.DBD0",          // Siemens S7 地址格式
    Type = DataType.Float,         // 数据类型：浮点数
    Length = 4,                    // 数据长度
    AnotherName = "温度传感器1",    // 别名
    Topic = "factory/line1/temp",  // 传输主题（可选）
    SimplifyValue = false          // 是否精简数据
};

// 2. 持久化到 SQLite
lock (GlobalConfigModel.DbLock)
{
    GlobalConfigModel.sqliteOperate.Insert(address);
}
GlobalConfigModel.AddressDict[address.Guid] = address;

// 3. 读取点位数据
var pluginConfig = GlobalConfigModel.PluginDict["device-sn-001"];
var result = await DqaHandler.Instance(pluginConfig).ReadAsync(pluginConfig.Guid, address);

// 4. 订阅点位变化（持续推送）
await DqaHandler.Instance(pluginConfig).SubscribeAsync(pluginConfig.Guid, address);
```

### 6.3 插件开发与热加载

```csharp
// === 开发一个 IDaq 插件 ===
// 1. 新建 .NET 类库项目，引用 Snet.Model
// 2. 实现 IDaq 接口：

public class MyDevicePlugin : IDaq
{
    public event EventHandlerAsync<EventDataResult> OnDataEventAsync;
    public event EventHandlerAsync<EventInfoResult> OnInfoEventAsync;

    public async Task<OperateResult> OnAsync()
    {
        // 连接设备
        return OperateResult.CreateSuccessResult("Connected");
    }

    public async Task<OperateResult> ReadAsync(Address address)
    {
        // 读取设备地址数据
        return OperateResult.CreateSuccessResult(data);
    }

    // ... 实现其他接口方法
}

// 3. 编译后打包为 ZIP
// 4. 在程序 UI "插件设置" 页面上传 ZIP → 自动热加载
```

### 6.4 配置数据流转 (DAQ → MQ)

```csharp
// 场景：Siemens PLC 温度数据 → MQTT Broker

// Step 1: 配置 DAQ 采集设备
var siemensConfig = new PluginConfigModel
{
    Type = PluginType.Daq,
    Name = "Snet.Siemens.SiemensDaq",
    Param = "{\"IP\":\"192.168.1.100\",\"Rack\":0,\"Slot\":1}",
    SN = "siemens-001"
};

// Step 2: 配置 MQTT 传输
var mqttConfig = new PluginConfigModel
{
    Type = PluginType.Mq,
    Name = "Snet.Mqtt.MqttMq",
    Param = "{\"Broker\":\"localhost\",\"Port\":1883}",
    SN = "mqtt-001"
};

// Step 3: 创建地址，绑定 Topic
var tempAddress = new AddressModel
{
    Address = "DB1.DBD0",
    Type = DataType.Float,
    Topic = "factory/temperature",  // ← 关键：绑定传输主题
    SimplifyValue = false,
    Guid = siemensConfig.Guid
};

// Step 4: 订阅采集数据 → 事件触发 → 自动生产到 MQTT
await DqaHandler.Instance(siemensConfig).SubscribeAsync(siemensConfig.Guid, tempAddress);

// 当 PLC 数据变化时：
// IDaq.OnDataEventAsync 触发 
// → DqaHandler 接收 (OpenAsync 中已注册事件)
// → 根据 address.Topic 调用 MqHandler.ProduceAsync
// → IMq 将数据发送到 MQTT Broker
```

### 6.5 内置 MQTT Server 启动

```csharp
// 启动内置 MQTT Broker
GlobalConfigModel.mqttService = new MqttServiceOperate();
await GlobalConfigModel.mqttService.StartAsync();

// 启动内置 OPC UA Server
GlobalConfigModel.uaService = new OpcUaServiceOperate();
await GlobalConfigModel.uaService.StartAsync();
```

### 6.6 目录结构约定

```
{AppContext.BaseDirectory}/
├── db/
│   └── address.db              # SQLite 数据库
├── lib/                         # 插件目录
│   ├── Snet.Siemens.Daq.Config.json
│   ├── Snet.Modbus.Daq.Config.json
│   └── Snet.Mqtt.Mq.Config.json
├── config/
│   ├── ui/
│   │   ├── PluginList.json      # 插件列表
│   │   ├── PluginConfig.json    # 插件配置
│   │   └── ProjectConfig.json   # 项目配置
│   └── server/
│       ├── MqttServerConfig.json
│       └── UaServerConfig.json
├── Snet.Iot.Daq.exe
└── Snet.Iot.Daq.Core.dll
```

---

## 附录

### 关键命名空间速查

| 命名空间 | 路径 | 说明 |
|----------|------|------|
| `Snet.Iot.Daq` | `Snet.Iot.Daq/` | WPF 主程序入口、App.xaml.cs |
| `Snet.Iot.Daq.data` | `Snet.Iot.Daq/data/` | UI 层数据模型、全局配置 |
| `Snet.Iot.Daq.view` | `Snet.Iot.Daq/view/` | WPF XAML 视图文件 |
| `Snet.Iot.Daq.viewModel` | `Snet.Iot.Daq/viewModel/` | MVVM ViewModel |
| `Snet.Iot.Daq.handler` | `Snet.Iot.Daq/handler/` | UI 层业务逻辑 |
| `Snet.Iot.Daq.Core.@interface` | `Snet.Iot.Daq.Core/interface/` | 核心接口定义 (`IAddressModel`) |
| `Snet.Iot.Daq.Core.data` | `Snet.Iot.Daq.Core/data/` | 核心数据模型 (`AddressModelCore`, `PluginConfigModel`) |
| `Snet.Iot.Daq.Core.handler` | `Snet.Iot.Daq.Core/handler/` | 核心处理器 (`DqaHandler`, `MqHandler`, `PluginHandlerCore`) |
| `Snet.Iot.Daq.Core.mqtt.service` | `Snet.Iot.Daq.Core/mqtt/service/` | 内置 MQTT Broker |
| `Snet.Iot.Daq.Core.opc.ua.service` | `Snet.Iot.Daq.Core/opc/ua/service/` | 内置 OPC UA Server |
| `Snet.Model.@interface` | 外部 NuGet | 插件接口 (`IDaq`, `IMq`) |
