// 23 种 GoF 设计模式模板：插入 UML 画布时自动生成对应类结构。
// 每个模式含：类/接口 + 关系（关联/继承/实现等）+ 关键属性/方法。
// 插入后仍可手动编辑、标注基数、生成代码 / MySQL。

export interface PatternClass {
  type?: 'class' | 'interface'
  name: string
  attributes?: string[]
  methods?: string[]
}
export interface PatternConnection {
  from: string
  to: string
  type: string // association / inheritance / realization / composition / aggregation / dependency
  cardinality?: string
}
export interface DesignPattern {
  key: string
  name: string
  en: string
  category: '创建型' | '结构型' | '行为型'
  desc: string
  classes: PatternClass[]
  connections: PatternConnection[]
}

let uidCounter = 0

/** 把模式模板铺到画布：自动排布（3 列网格）+ 分配唯一 id */
export const buildPatternElements = (pattern: DesignPattern, offX: number, offY: number) => {
  const elements: any[] = []
  const idMap: Record<string, string> = {}
  const cols = Math.min(3, pattern.classes.length)
  pattern.classes.forEach((c, i) => {
    const id = 'dp' + (++uidCounter)
    idMap[c.name] = id
    const col = i % cols
    const row = Math.floor(i / cols)
    const isIface = c.type === 'interface'
    elements.push({
      id,
      type: isIface ? 'interface' : 'class',
      name: c.name,
      x: offX + col * 200,
      y: offY + row * 160,
      width: 150,
      height: 100,
      color: '#ffffff',
      headerColor: isIface ? '#4caf50' : '#1f5eff',
      attributes: c.attributes || [],
      methods: c.methods || []
    })
  })
  const connections = pattern.connections.map((c) => ({
    id: 'dpc' + (++uidCounter),
    type: c.type,
    startElement: idMap[c.from],
    endElement: idMap[c.to],
    cardinality: c.cardinality || 'oneToMany'
  }))
  return { elements, connections }
}

export const designPatterns: DesignPattern[] = [
  // ============ 创建型（5）============
  {
    key: 'singleton', name: '单例模式', en: 'Singleton', category: '创建型',
    desc: '保证一个类仅有一个实例，并提供一个全局访问点',
    classes: [
      { name: 'Singleton', attributes: ['- instance: Singleton'], methods: ['+ getInstance(): Singleton', '- Singleton()'] }
    ],
    connections: []
  },
  {
    key: 'factory-method', name: '工厂方法', en: 'Factory Method', category: '创建型',
    desc: '定义创建对象的接口，由子类决定实例化哪个类',
    classes: [
      { name: 'Product', type: 'interface', methods: ['+ use(): void'] },
      { name: 'ConcreteProduct', methods: ['+ use(): void'] },
      { name: 'Creator', methods: ['+ factoryMethod(): Product', '+ operation(): void'] },
      { name: 'ConcreteCreator', methods: ['+ factoryMethod(): Product'] }
    ],
    connections: [
      { from: 'ConcreteProduct', to: 'Product', type: 'realization' },
      { from: 'ConcreteCreator', to: 'Creator', type: 'inheritance' },
      { from: 'Creator', to: 'Product', type: 'association' }
    ]
  },
  {
    key: 'abstract-factory', name: '抽象工厂', en: 'Abstract Factory', category: '创建型',
    desc: '提供一个创建一系列相关对象的接口，无需指定具体类',
    classes: [
      { name: 'AbstractFactory', type: 'interface', methods: ['+ createProductA(): ProductA', '+ createProductB(): ProductB'] },
      { name: 'ConcreteFactory', methods: ['+ createProductA(): ProductA', '+ createProductB(): ProductB'] },
      { name: 'ProductA', type: 'interface', methods: ['+ use(): void'] },
      { name: 'ProductA1', methods: ['+ use(): void'] }
    ],
    connections: [
      { from: 'ConcreteFactory', to: 'AbstractFactory', type: 'realization' },
      { from: 'ProductA1', to: 'ProductA', type: 'realization' },
      { from: 'AbstractFactory', to: 'ProductA', type: 'association' }
    ]
  },
  {
    key: 'builder', name: '建造者模式', en: 'Builder', category: '创建型',
    desc: '将一个复杂对象的构建与表示分离，同样的构建过程可创建不同表示',
    classes: [
      { name: 'Builder', type: 'interface', methods: ['+ buildPart(): void'] },
      { name: 'ConcreteBuilder', methods: ['+ buildPart(): void', '+ getResult(): Product'] },
      { name: 'Director', methods: ['+ construct(builder: Builder): void'] },
      { name: 'Product', attributes: ['- parts: List<String>'] }
    ],
    connections: [
      { from: 'ConcreteBuilder', to: 'Builder', type: 'realization' },
      { from: 'Director', to: 'Builder', type: 'association' },
      { from: 'ConcreteBuilder', to: 'Product', type: 'association' }
    ]
  },
  {
    key: 'prototype', name: '原型模式', en: 'Prototype', category: '创建型',
    desc: '用原型实例指定创建对象的种类，并通过拷贝这些原型创建新对象',
    classes: [
      { name: 'Prototype', type: 'interface', methods: ['+ clone(): Prototype'] },
      { name: 'ConcretePrototype', attributes: ['- data: String'], methods: ['+ clone(): Prototype'] }
    ],
    connections: [
      { from: 'ConcretePrototype', to: 'Prototype', type: 'realization' }
    ]
  },

  // ============ 结构型（7）============
  {
    key: 'adapter', name: '适配器模式', en: 'Adapter', category: '结构型',
    desc: '将一个类的接口转换成客户期望的另一个接口',
    classes: [
      { name: 'Target', type: 'interface', methods: ['+ request(): void'] },
      { name: 'Adapter', methods: ['+ request(): void'] },
      { name: 'Adaptee', methods: ['+ specificRequest(): void'] }
    ],
    connections: [
      { from: 'Adapter', to: 'Target', type: 'realization' },
      { from: 'Adapter', to: 'Adaptee', type: 'association' }
    ]
  },
  {
    key: 'bridge', name: '桥接模式', en: 'Bridge', category: '结构型',
    desc: '将抽象部分与实现部分分离，使它们可以独立变化',
    classes: [
      { name: 'Abstraction', methods: ['+ operation(): void'] },
      { name: 'RefinedAbstraction', methods: ['+ operation(): void'] },
      { name: 'Implementor', type: 'interface', methods: ['+ operationImpl(): void'] },
      { name: 'ConcreteImplementor', methods: ['+ operationImpl(): void'] }
    ],
    connections: [
      { from: 'RefinedAbstraction', to: 'Abstraction', type: 'inheritance' },
      { from: 'Abstraction', to: 'Implementor', type: 'association' },
      { from: 'ConcreteImplementor', to: 'Implementor', type: 'realization' }
    ]
  },
  {
    key: 'composite', name: '组合模式', en: 'Composite', category: '结构型',
    desc: '将对象组合成树形结构以表示部分-整体层次，客户端可一致处理单个与组合对象',
    classes: [
      { name: 'Component', type: 'interface', methods: ['+ operation(): void', '+ add(c: Component): void'] },
      { name: 'Leaf', methods: ['+ operation(): void'] },
      { name: 'Composite', attributes: ['- children: List<Component>'], methods: ['+ operation(): void', '+ add(c: Component): void'] }
    ],
    connections: [
      { from: 'Leaf', to: 'Component', type: 'realization' },
      { from: 'Composite', to: 'Component', type: 'realization' },
      { from: 'Composite', to: 'Component', type: 'association' }
    ]
  },
  {
    key: 'decorator', name: '装饰器模式', en: 'Decorator', category: '结构型',
    desc: '动态地给对象添加额外职责，比继承更灵活',
    classes: [
      { name: 'Component', type: 'interface', methods: ['+ operation(): void'] },
      { name: 'ConcreteComponent', methods: ['+ operation(): void'] },
      { name: 'Decorator', methods: ['+ operation(): void'] },
      { name: 'ConcreteDecorator', methods: ['+ operation(): void'] }
    ],
    connections: [
      { from: 'ConcreteComponent', to: 'Component', type: 'realization' },
      { from: 'Decorator', to: 'Component', type: 'realization' },
      { from: 'Decorator', to: 'Component', type: 'association' },
      { from: 'ConcreteDecorator', to: 'Decorator', type: 'inheritance' }
    ]
  },
  {
    key: 'facade', name: '外观模式', en: 'Facade', category: '结构型',
    desc: '为子系统中的一组接口提供一个统一的高层接口',
    classes: [
      { name: 'Facade', methods: ['+ simpleOperation(): void'] },
      { name: 'SubsystemA', methods: ['+ opA(): void'] },
      { name: 'SubsystemB', methods: ['+ opB(): void'] },
      { name: 'SubsystemC', methods: ['+ opC(): void'] }
    ],
    connections: [
      { from: 'Facade', to: 'SubsystemA', type: 'association' },
      { from: 'Facade', to: 'SubsystemB', type: 'association' },
      { from: 'Facade', to: 'SubsystemC', type: 'association' }
    ]
  },
  {
    key: 'flyweight', name: '享元模式', en: 'Flyweight', category: '结构型',
    desc: '共享细粒度对象以减少内存占用，通过工厂管理享元实例',
    classes: [
      { name: 'Flyweight', type: 'interface', methods: ['+ operation(ext: String): void'] },
      { name: 'ConcreteFlyweight', methods: ['+ operation(ext: String): void'] },
      { name: 'FlyweightFactory', attributes: ['- pool: Map<String, Flyweight>'], methods: ['+ getFlyweight(key: String): Flyweight'] }
    ],
    connections: [
      { from: 'ConcreteFlyweight', to: 'Flyweight', type: 'realization' },
      { from: 'FlyweightFactory', to: 'Flyweight', type: 'association' }
    ]
  },
  {
    key: 'proxy', name: '代理模式', en: 'Proxy', category: '结构型',
    desc: '为其他对象提供一种代理以控制对这个对象的访问',
    classes: [
      { name: 'Subject', type: 'interface', methods: ['+ request(): void'] },
      { name: 'RealSubject', methods: ['+ request(): void'] },
      { name: 'Proxy', attributes: ['- real: RealSubject'], methods: ['+ request(): void'] }
    ],
    connections: [
      { from: 'RealSubject', to: 'Subject', type: 'realization' },
      { from: 'Proxy', to: 'Subject', type: 'realization' },
      { from: 'Proxy', to: 'RealSubject', type: 'association' }
    ]
  },

  // ============ 行为型（11）============
  {
    key: 'chain', name: '责任链模式', en: 'Chain of Responsibility', category: '行为型',
    desc: '将请求的发送者与接收者解耦，多个对象链式处理请求',
    classes: [
      { name: 'Handler', type: 'interface', methods: ['+ setNext(h: Handler): Handler', '+ handle(req: String): void'] },
      { name: 'ConcreteHandler1', methods: ['+ handle(req: String): void'] },
      { name: 'ConcreteHandler2', methods: ['+ handle(req: String): void'] }
    ],
    connections: [
      { from: 'ConcreteHandler1', to: 'Handler', type: 'realization' },
      { from: 'ConcreteHandler2', to: 'Handler', type: 'realization' },
      { from: 'Handler', to: 'Handler', type: 'association' }
    ]
  },
  {
    key: 'command', name: '命令模式', en: 'Command', category: '行为型',
    desc: '将请求封装为对象，支持撤销、队列、日志等',
    classes: [
      { name: 'Command', type: 'interface', methods: ['+ execute(): void'] },
      { name: 'ConcreteCommand', methods: ['+ execute(): void'] },
      { name: 'Receiver', methods: ['+ action(): void'] },
      { name: 'Invoker', methods: ['+ setCommand(c: Command): void', '+ invoke(): void'] }
    ],
    connections: [
      { from: 'ConcreteCommand', to: 'Command', type: 'realization' },
      { from: 'ConcreteCommand', to: 'Receiver', type: 'association' },
      { from: 'Invoker', to: 'Command', type: 'association' }
    ]
  },
  {
    key: 'interpreter', name: '解释器模式', en: 'Interpreter', category: '行为型',
    desc: '为语言定义文法表示并解释执行句子',
    classes: [
      { name: 'Expression', type: 'interface', methods: ['+ interpret(ctx: Context): void'] },
      { name: 'TerminalExpression', methods: ['+ interpret(ctx: Context): void'] },
      { name: 'NonterminalExpression', methods: ['+ interpret(ctx: Context): void'] }
    ],
    connections: [
      { from: 'TerminalExpression', to: 'Expression', type: 'realization' },
      { from: 'NonterminalExpression', to: 'Expression', type: 'realization' },
      { from: 'NonterminalExpression', to: 'Expression', type: 'association' }
    ]
  },
  {
    key: 'iterator', name: '迭代器模式', en: 'Iterator', category: '行为型',
    desc: '顺序访问集合对象元素而不暴露内部表示',
    classes: [
      { name: 'Iterator', type: 'interface', methods: ['+ hasNext(): boolean', '+ next(): Object'] },
      { name: 'ConcreteIterator', methods: ['+ hasNext(): boolean', '+ next(): Object'] },
      { name: 'Aggregate', type: 'interface', methods: ['+ createIterator(): Iterator'] },
      { name: 'ConcreteAggregate', methods: ['+ createIterator(): Iterator'] }
    ],
    connections: [
      { from: 'ConcreteIterator', to: 'Iterator', type: 'realization' },
      { from: 'ConcreteAggregate', to: 'Aggregate', type: 'realization' },
      { from: 'ConcreteAggregate', to: 'Iterator', type: 'association' }
    ]
  },
  {
    key: 'mediator', name: '中介者模式', en: 'Mediator', category: '行为型',
    desc: '用一个中介对象封装一组对象的交互，避免对象间直接耦合',
    classes: [
      { name: 'Mediator', type: 'interface', methods: ['+ notify(sender: Colleague): void'] },
      { name: 'ConcreteMediator', methods: ['+ notify(sender: Colleague): void'] },
      { name: 'Colleague', type: 'interface', methods: ['+ send(msg: String): void'] },
      { name: 'ConcreteColleague1', methods: ['+ send(msg: String): void'] },
      { name: 'ConcreteColleague2', methods: ['+ send(msg: String): void'] }
    ],
    connections: [
      { from: 'ConcreteMediator', to: 'Mediator', type: 'realization' },
      { from: 'ConcreteColleague1', to: 'Colleague', type: 'realization' },
      { from: 'ConcreteColleague2', to: 'Colleague', type: 'realization' },
      { from: 'Colleague', to: 'Mediator', type: 'association' }
    ]
  },
  {
    key: 'memento', name: '备忘录模式', en: 'Memento', category: '行为型',
    desc: '在不破坏封装的前提下捕获并外部化对象内部状态，便于恢复',
    classes: [
      { name: 'Memento', attributes: ['- state: String'], methods: ['+ getState(): String'] },
      { name: 'Originator', attributes: ['- state: String'], methods: ['+ createMemento(): Memento', '+ restore(m: Memento): void'] },
      { name: 'Caretaker', attributes: ['- memento: Memento'] }
    ],
    connections: [
      { from: 'Originator', to: 'Memento', type: 'association' },
      { from: 'Caretaker', to: 'Memento', type: 'association' }
    ]
  },
  {
    key: 'observer', name: '观察者模式', en: 'Observer', category: '行为型',
    desc: '定义对象间一对多的依赖，一个对象变化时自动通知并更新其他对象',
    classes: [
      { name: 'Subject', type: 'interface', methods: ['+ attach(o: Observer): void', '+ detach(o: Observer): void', '+ notify(): void'] },
      { name: 'Observer', type: 'interface', methods: ['+ update(): void'] },
      { name: 'ConcreteSubject', attributes: ['- observers: List<Observer>', '- state: int'], methods: ['+ attach(o: Observer): void', '+ notify(): void'] },
      { name: 'ConcreteObserver', attributes: ['- subject: ConcreteSubject'], methods: ['+ update(): void'] }
    ],
    connections: [
      { from: 'ConcreteSubject', to: 'Subject', type: 'realization' },
      { from: 'ConcreteObserver', to: 'Observer', type: 'realization' },
      { from: 'Subject', to: 'Observer', type: 'association', cardinality: 'oneToMany' }
    ]
  },
  {
    key: 'state', name: '状态模式', en: 'State', category: '行为型',
    desc: '对象行为随内部状态改变而改变，将状态行为封装为独立类',
    classes: [
      { name: 'State', type: 'interface', methods: ['+ handle(ctx: Context): void'] },
      { name: 'ConcreteStateA', methods: ['+ handle(ctx: Context): void'] },
      { name: 'ConcreteStateB', methods: ['+ handle(ctx: Context): void'] },
      { name: 'Context', attributes: ['- state: State'], methods: ['+ setState(s: State): void', '+ request(): void'] }
    ],
    connections: [
      { from: 'ConcreteStateA', to: 'State', type: 'realization' },
      { from: 'ConcreteStateB', to: 'State', type: 'realization' },
      { from: 'Context', to: 'State', type: 'association' }
    ]
  },
  {
    key: 'strategy', name: '策略模式', en: 'Strategy', category: '行为型',
    desc: '定义一族算法，封装起来使其可互换，算法变化独立于使用它的客户端',
    classes: [
      { name: 'Strategy', type: 'interface', methods: ['+ execute(): void'] },
      { name: 'ConcreteStrategyA', methods: ['+ execute(): void'] },
      { name: 'ConcreteStrategyB', methods: ['+ execute(): void'] },
      { name: 'Context', attributes: ['- strategy: Strategy'], methods: ['+ setStrategy(s: Strategy): void', '+ doWork(): void'] }
    ],
    connections: [
      { from: 'ConcreteStrategyA', to: 'Strategy', type: 'realization' },
      { from: 'ConcreteStrategyB', to: 'Strategy', type: 'realization' },
      { from: 'Context', to: 'Strategy', type: 'association' }
    ]
  },
  {
    key: 'template-method', name: '模板方法', en: 'Template Method', category: '行为型',
    desc: '在父类中定义算法骨架，将步骤延迟到子类实现',
    classes: [
      { name: 'AbstractClass', methods: ['+ templateMethod(): void', '+ step1(): void', '+ step2(): void'] },
      { name: 'ConcreteClass', methods: ['+ step1(): void', '+ step2(): void'] }
    ],
    connections: [
      { from: 'ConcreteClass', to: 'AbstractClass', type: 'inheritance' }
    ]
  },
  {
    key: 'visitor', name: '访问者模式', en: 'Visitor', category: '行为型',
    desc: '将数据结构与作用于其上的操作分离，新增操作无需修改元素类',
    classes: [
      { name: 'Visitor', type: 'interface', methods: ['+ visit(e: Element): void'] },
      { name: 'ConcreteVisitor', methods: ['+ visit(e: Element): void'] },
      { name: 'Element', type: 'interface', methods: ['+ accept(v: Visitor): void'] },
      { name: 'ConcreteElementA', methods: ['+ accept(v: Visitor): void'] },
      { name: 'ConcreteElementB', methods: ['+ accept(v: Visitor): void'] }
    ],
    connections: [
      { from: 'ConcreteVisitor', to: 'Visitor', type: 'realization' },
      { from: 'ConcreteElementA', to: 'Element', type: 'realization' },
      { from: 'ConcreteElementB', to: 'Element', type: 'realization' },
      { from: 'Element', to: 'Visitor', type: 'association' }
    ]
  }
]

export const patternCategories: Array<'创建型' | '结构型' | '行为型'> = ['创建型', '结构型', '行为型']
