import { useState } from "react";

type Lead = {
  id: string;
  source_platform?: string;
  customer_name?: string;
  contact_person?: string;
  product_title?: string;
  quantity?: string;
  missing_info?: string;
  intent_level?: string;
  suggested_reply?: string;
  customer_id: string;
  status: string;
};

type Customer = {
  id: string;
  customer_name?: string;
  contact_person?: string;
  region?: string;
  contact?: string;
  source_platform?: string;
  lead_count: number;
  pending_count: number;
  customer_status?: string;
  summary?: string;
};

export function DataView({ leads, customers }: { leads: Lead[]; customers: Customer[] }) {
  const [tab, setTab] = useState<"leads" | "customers">("leads");
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>业务数据</h2>
        <div className="segmented">
          <button className={tab === "leads" ? "active" : ""} onClick={() => setTab("leads")}>
            线索
          </button>
          <button className={tab === "customers" ? "active" : ""} onClick={() => setTab("customers")}>
            客户
          </button>
        </div>
      </div>
      {tab === "leads" ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>客户</th>
                <th>联系人</th>
                <th>平台</th>
                <th>商品</th>
                <th>数量</th>
                <th>意向</th>
                <th>缺失信息</th>
                <th>建议回复</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td>{lead.customer_name}</td>
                  <td>{lead.contact_person || "-"}</td>
                  <td>{lead.source_platform}</td>
                  <td>{lead.product_title || "-"}</td>
                  <td>{lead.quantity || "-"}</td>
                  <td>{lead.intent_level}</td>
                  <td>{lead.missing_info || "-"}</td>
                  <td className="summary-cell">{lead.suggested_reply}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>客户</th>
                <th>联系人</th>
                <th>地区</th>
                <th>来源</th>
                <th>联系方式</th>
                <th>线索数</th>
                <th>待处理</th>
                <th>状态</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((customer) => (
                <tr key={customer.id}>
                  <td>{customer.customer_name}</td>
                  <td>{customer.contact_person || "-"}</td>
                  <td>{customer.region || "-"}</td>
                  <td>{customer.source_platform || "-"}</td>
                  <td>{customer.contact || "-"}</td>
                  <td>{customer.lead_count}</td>
                  <td>{customer.pending_count}</td>
                  <td>{customer.customer_status || "-"}</td>
                  <td className="summary-cell">{customer.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
