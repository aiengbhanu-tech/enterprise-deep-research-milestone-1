async def _require_run(
    run_id: UUID,
    session: DbSession,
) -> None:
    if (
        await session.get(
            ResearchRun,
            run_id,
        )
        is None
    ):
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )


@router.get(
    "/runs/{run_id}/coverage",
    response_model=list[CoverageRead],
)
async def list_coverage(
    run_id: UUID,
    session: DbSession,
) -> list[CoverageAssessment]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(CoverageAssessment)
            .where(
                CoverageAssessment.run_id
                == run_id
            )
            .order_by(
                CoverageAssessment.iteration,
                CoverageAssessment.question_id,
            )
        )
    )


@router.get(
    "/runs/{run_id}/gaps",
    response_model=list[ResearchGapRead],
)
async def list_gaps(
    run_id: UUID,
    session: DbSession,
) -> list[ResearchGap]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(ResearchGap)
            .where(
                ResearchGap.run_id == run_id
            )
            .order_by(
                ResearchGap.iteration,
                ResearchGap.question_id,
            )
        )
    )


@router.get(
    "/runs/{run_id}/contradictions",
    response_model=list[ContradictionRead],
)
async def list_contradictions(
    run_id: UUID,
    session: DbSession,
) -> list[Contradiction]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(Contradiction)
            .where(
                Contradiction.run_id == run_id
            )
            .order_by(
                Contradiction.iteration
            )
        )
    )


@router.get(
    "/runs/{run_id}/critic",
    response_model=list[CriticReviewRead],
)
async def list_critic_reviews(
    run_id: UUID,
    session: DbSession,
) -> list[CriticReview]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(CriticReview)
            .where(
                CriticReview.run_id == run_id
            )
            .order_by(
                CriticReview.iteration
            )
        )
    )