import api from './api'
import type {
  DashboardData,
  KPICard,
  AgingBucket,
  WorkloadItem,
  DetectorStat,
} from '../types'

export async function getDashboard(): Promise<DashboardData> {
  const res = await api.get<DashboardData>('/dashboard')
  return res.data
}

export async function getKPIs(): Promise<KPICard[]> {
  const res = await api.get<KPICard[]>('/dashboard/kpis')
  return res.data
}

export async function getAging(): Promise<AgingBucket[]> {
  const res = await api.get<AgingBucket[]>('/dashboard/aging')
  return res.data
}

export async function getWorkload(): Promise<WorkloadItem[]> {
  const res = await api.get<WorkloadItem[]>('/dashboard/workload')
  return res.data
}

export async function getDetectorStats(): Promise<DetectorStat[]> {
  const res = await api.get<DetectorStat[]>('/dashboard/detectors')
  return res.data
}
