import React, { createContext, useContext, useEffect, useState } from "react";
import { Tenant, fetchTenants } from "../api/client";

interface TenantContextValue {
  tenants: Tenant[];
  currentTenant: Tenant | null;
  setCurrentTenant: (t: Tenant) => void;
  loading: boolean;
}

const TenantContext = createContext<TenantContextValue>({
  tenants: [],
  currentTenant: null,
  setCurrentTenant: () => {},
  loading: true,
});

const STORAGE_KEY = "selectedTenantId";

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [currentTenant, setCurrentTenantState] = useState<Tenant | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTenants().then((list) => {
      setTenants(list);
      const savedId = localStorage.getItem(STORAGE_KEY);
      const saved = list.find((t) => t.id === savedId) ?? list[0] ?? null;
      setCurrentTenantState(saved);
      setLoading(false);
    });
  }, []);

  const setCurrentTenant = (t: Tenant) => {
    localStorage.setItem(STORAGE_KEY, t.id);
    setCurrentTenantState(t);
  };

  return (
    <TenantContext.Provider value={{ tenants, currentTenant, loading, setCurrentTenant }}>
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant(): TenantContextValue {
  return useContext(TenantContext);
}
