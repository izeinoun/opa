export const colors = {
  primary: '#FE017D',
  navy:    '#1e3a5f',
  teal:    '#0d9488',
  purple:  '#7c3aed',
}

export const priorityBadge = {
  high:   'bg-amber-100 text-amber-700 border border-amber-200',
  medium: 'bg-blue-100 text-blue-700 border border-blue-200',
  low:    'bg-green-100 text-green-700 border border-green-200',
}

export const statusBadge: Record<string, string> = {
  new:                   'bg-gray-100 text-gray-600',
  assigned:              'bg-blue-100 text-blue-700',
  in_review:             'bg-amber-100 text-amber-700',
  pending_supervisor:    'bg-purple-100 text-purple-700',
  notice_sent:           'bg-teal-100 text-teal-700',
  provider_responded:    'bg-blue-100 text-blue-700',
  reconciling:           'bg-amber-100 text-amber-700',
  closed_recovered:      'bg-green-100 text-green-700',
  closed_written_off:    'bg-gray-100 text-gray-500',
  closed_overturned:     'bg-red-100 text-red-700',
  closed_no_overpayment: 'bg-gray-100 text-gray-500',
  closed_not_for_recoup: 'bg-gray-100 text-gray-500',
  // aliases from DB
  identified:                   'bg-gray-100 text-gray-600',
  in_review_db:                 'bg-amber-100 text-amber-700',
  pending_provider_response:    'bg-blue-100 text-blue-700',
  pending_dispute:              'bg-purple-100 text-purple-700',
  closed_unrecoverable:         'bg-gray-100 text-gray-500',
}

export const detectorBadge: Record<string, string> = {
  'DET-01': 'bg-blue-100 text-blue-700',
  'DET-02': 'bg-amber-100 text-amber-700',
  'DET-04': 'bg-red-100 text-red-700',
  'DET-06': 'bg-orange-100 text-orange-700',
  'DET-08': 'bg-red-100 text-red-700',
  'DET-09': 'bg-purple-100 text-purple-700',
  'EXCESS_UNITS_V1':       'bg-amber-100 text-amber-700',
  'UPCODING_V1':           'bg-orange-100 text-orange-700',
  'DUPLICATE_CLAIM_V1':    'bg-blue-100 text-blue-700',
  'DX_CPT_MISMATCH_V1':    'bg-red-100 text-red-700',
  'BILLING_VARIANCE_V1':   'bg-purple-100 text-purple-700',
  'RETRO_TERM_V1':         'bg-pink-100 text-pink-700',
  'POST_DEATH_V1':         'bg-red-100 text-red-700',
  'MULTI_LINE_COMPLEXITY_V1': 'bg-teal-100 text-teal-700',
  'GENERAL_REVIEW_V1':     'bg-gray-100 text-gray-600',
}

export const card = 'bg-white rounded-xl border border-gray-200 shadow-sm p-4'
