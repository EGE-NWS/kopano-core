/*
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright 2005 - 2016 Zarafa and its licensors
 */

/**
 * @file
 * Free/busy data blocks
 *
 * @addtogroup libfreebusy
 * @{
 */
#pragma once
#include "freebusy.h"
#include <kopano/ECUnknown.h>
#include <kopano/ECGuid.h>
#include <kopano/Util.h>
#include <kopano/zcdefs.h>
#include "freebusyguid.h"
#include "ECFBBlockList.h"

namespace KC {

/**
 * Implementatie of the IEnumFBBlock interface
 */
class ECEnumFBBlock KC_FINAL_OPG : public ECUnknown, public IEnumFBBlock {
private:
	ECEnumFBBlock(ECFBBlockList* lpFBBlock);
public:
	static HRESULT Create(ECFBBlockList* lpFBBlock, ECEnumFBBlock **lppECEnumFBBlock);
	virtual HRESULT QueryInterface(const IID &, void **) override;
	virtual HRESULT Next(int nelem, FBBlock_1 *pblk, int *nfetch) override;
	virtual HRESULT Skip(int nelem) override { return m_FBBlock.Skip(nelem); }
	virtual HRESULT Reset() override { return m_FBBlock.Reset(); }
	virtual HRESULT Clone(IEnumFBBlock **) override { return E_NOTIMPL; }
	virtual HRESULT Restrict(const FILETIME &start, const FILETIME &end) override;

	ECFBBlockList	m_FBBlock; /**< Freebusy time blocks */
	ALLOC_WRAP_FRIEND;
};

} /* namespace */

/** @} */
