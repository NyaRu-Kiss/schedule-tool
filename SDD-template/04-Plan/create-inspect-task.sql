IF OBJECT_ID(N'VOV_DealerVehicleInspectTask', N'U') IS NULL
BEGIN
    CREATE TABLE [VOV_DealerVehicleInspectTask] (
        [ID]                     int              IDENTITY(1,1) NOT NULL,
        [InspectCode]            nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NOT NULL,
        [Source]                 nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NOT NULL DEFAULT (N'MANUAL'),
        [LtoTaskId]              nvarchar(100)    COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [DealerCode]             nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NOT NULL,
        [VehicleID]              uniqueidentifier NULL,
        [VehicleModelId]         nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [CarSeries]              nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [Vin]                    nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [PlateNumber]            nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [BodyColor]              nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [Mileage]                nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [Owner]                  nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [OwnerType]              nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [TransferCount]          int              NULL,
        [UseType]                nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [FactoryDate]            nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [FirstLicenseDate]       nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [AnnualInspectionExpiry] nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [InspectUserId]          int              NOT NULL DEFAULT ((0)),
        [InspectUserName]        nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [DrivingLicensePhoto]    ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IdCardPhotos]           ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IdCardNumber]           nvarchar(30)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [CustomerName]           nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [CustomerPhone]          nvarchar(20)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [ExteriorPhotos]         ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [InteriorPhotos]         ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [VinKeyPhotos]           ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [VehicleDocPhotos]       ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsBurned]               bit              NOT NULL DEFAULT ((0)),
        [BurnedPhotos]           ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsFlooded]              bit              NOT NULL DEFAULT ((0)),
        [FloodedPhotos]          ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsFrameAccident]        bit              NOT NULL DEFAULT ((0)),
        [FrameAccidentPhotos]    ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [ModificationType]       nvarchar(100)    COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsOdometerTampered]     bit              NOT NULL DEFAULT ((0)),
        [OdometerTamperedPhotos] ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsNameplateMissing]     bit              NOT NULL DEFAULT ((0)),
        [NameplatePhotos]        ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [InspectData]            ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [PaintThicknessData]     ntext            COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsPriceNegotiable]      bit              NOT NULL DEFAULT ((0)),
        [EstimatedPrice]         decimal(18,2)    NULL,
        [TotalTransactionPrice]  decimal(18,2)    NULL,
        [ResidualValueAmount]    decimal(18,2)    NULL,
        [SubsidyAmount]          decimal(18,2)    NULL,
        [ReportStatus]           int              NOT NULL DEFAULT ((0)),
        [ReportToken]            nvarchar(100)    COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [IsViewed]               bit              NOT NULL DEFAULT ((0)),
        [InspectTime]            datetime         NULL,
        [ViewedTime]             datetime         NULL,
        [SmsCode]                nvarchar(10)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [SmsCodeExpire]          datetime         NULL,
        [CreateTime]             datetime         NOT NULL DEFAULT (getdate()),
        [UpdateTime]             datetime         NULL,
        [BrandID]                nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [BrandName]              nvarchar(100)    COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [SeriesID]               nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [SeriesName]             nvarchar(100)    COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [ModelID]                nvarchar(50)     COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        [ModelName]              nvarchar(200)    COLLATE SQL_Latin1_General_CP1_CI_AS NULL,
        CONSTRAINT [PK_VOV_DealerVehicleInspectTask] PRIMARY KEY ([ID])
    );

    CREATE UNIQUE INDEX [IX_InspectTask_ReportToken]
        ON [VOV_DealerVehicleInspectTask] ([ReportToken])
        WHERE ([ReportToken] IS NOT NULL);

    CREATE INDEX [IX_InspectTask_DealerCode_CreateTime]
        ON [VOV_DealerVehicleInspectTask] ([DealerCode], [CreateTime] DESC);

    CREATE INDEX [IX_InspectTask_Status_CreateTime]
        ON [VOV_DealerVehicleInspectTask] ([ReportStatus], [CreateTime] DESC);

    PRINT N'VOV_DealerVehicleInspectTask 创建成功';
END
ELSE
BEGIN
    PRINT N'VOV_DealerVehicleInspectTask 已存在，跳过';
END
GO
